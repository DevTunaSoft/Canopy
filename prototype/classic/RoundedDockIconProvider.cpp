#include "RoundedDockIconProvider.h"

#include <QDir>
#include <QFile>
#include <QImageReader>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPainter>
#include <QPainterPath>

namespace {
constexpr int kCanvasPixels = 192;
constexpr int kInsetPixels = 12;
constexpr int kRoundedRadius = 36;
constexpr int kMaxRequestPixels = 256;

// Measured center points of each original icon's brighter illustration
// pixels (2%-98% bounds). They are a review-only optical guide, NOT a
// judgment of aesthetics. Keep the complete original source rectangle:
// the prior 324px-square trial clipped some bright border pixels.
constexpr int kReviewInsetPixels = 5;
constexpr qreal kReviewOffsetGain = 1.75;
const QHash<QString, QPointF> kLauncherOpticalCenters = {
    {QStringLiteral("browser"), QPointF(170, 170)},
    {QStringLiteral("mail"), QPointF(172, 162)},
    {QStringLiteral("files"), QPointF(174, 164)},
    {QStringLiteral("calendar"), QPointF(173, 165)},
    {QStringLiteral("photos"), QPointF(171, 166)},
    {QStringLiteral("music"), QPointF(172, 169)},
    {QStringLiteral("terminal"), QPointF(171, 170)},
    {QStringLiteral("settings"), QPointF(175, 165)},
};
}

RoundedDockIconProvider::RoundedDockIconProvider(
    const QString &approvedRoot, const QString &terminalCandidatePath,
    bool framingReviewMode, QString *error)
    : QQuickImageProvider(QQuickImageProvider::Image) {
    QFile manifest(QStringLiteral(":/Canopy/Classic/assets/approved/manifest.json"));
    if (!manifest.open(QIODevice::ReadOnly)) {
        *error = QStringLiteral("embedded icon manifest missing");
        return;
    }
    const QJsonDocument json = QJsonDocument::fromJson(manifest.readAll());
    if (!json.isObject()) {
        *error = QStringLiteral("embedded icon manifest invalid");
        return;
    }
    const QJsonArray entries = json.object().value(QStringLiteral("icons")).toArray();
    if (entries.size() != 8) {
        *error = QStringLiteral("expected exactly eight original icon masters");
        return;
    }

    const QDir root(approvedRoot);
    for (const QJsonValue &entry : entries) {
        const QJsonObject row = entry.toObject();
        const QString id = row.value(QStringLiteral("name")).toString().toLower();
        const QString relative = row.value(QStringLiteral("path")).toString();
        if (id.isEmpty() || relative.isEmpty() || m_images.contains(id)) {
            *error = QStringLiteral("missing or duplicate dock icon");
            m_images.clear();
            return;
        }

        // Source verification, including SHA-256, has already succeeded in
        // verifyExactArtwork() before this constructor can be called.
        // Only Terminal may use an explicitly supplied visual candidate.
        // All eight immutable masters were verified BEFORE the provider runs.
        const QString sourcePath =
            id == QStringLiteral("terminal") && !terminalCandidatePath.isEmpty()
                ? terminalCandidatePath : root.filePath(relative);
        QImageReader reader(sourcePath);
        const QImage original = reader.read();
        if (original.isNull()) {
            *error = QStringLiteral("verified icon cannot be decoded: ") + id;
            m_images.clear();
            return;
        }

        QImage rendered(kCanvasPixels, kCanvasPixels,
                        QImage::Format_ARGB32_Premultiplied);
        rendered.fill(Qt::transparent);
        QPainter painter(&rendered);
        painter.setRenderHint(QPainter::Antialiasing, true);
        painter.setRenderHint(QPainter::SmoothPixmapTransform, true);

        const QRectF face(kInsetPixels, kInsetPixels,
                          kCanvasPixels - 2 * kInsetPixels,
                          kCanvasPixels - 2 * kInsetPixels);
        QPainterPath outline;
        outline.addRoundedRect(face, kRoundedRadius, kRoundedRadius);
        painter.setClipPath(outline);
        painter.fillPath(outline, QColor(QStringLiteral("#10203d")));

        const bool terminalDerivative =
            !terminalCandidatePath.isEmpty() && sourcePath == terminalCandidatePath;
        if (framingReviewMode && !terminalDerivative) {
            // Candidate C is launcher-only. Never sample a sub-rectangle
            // from the approved PNG: the last 324px source crop was found to
            // discard 3-7% of bright edge pixels. Instead fit the ENTIRE
            // source image in a slightly inset, centered target and shift
            // its content conservatively using measured bright-art centers.
            // Dock always takes the full-fit ELSE branch below.
            if (!kLauncherOpticalCenters.contains(id) ||
                original.width() != 345 ||
                (original.height() != 333 && original.height() != 334)) {
                *error = QStringLiteral("launcher optical review input mismatch");
                m_images.clear();
                return;
            }
            const QPointF contentCenter = kLauncherOpticalCenters.value(id);
            const QPointF canvasCenter((original.width() - 1.0) / 2.0,
                                       (original.height() - 1.0) / 2.0);
            const QRectF insetFace = face.adjusted(
                kReviewInsetPixels, kReviewInsetPixels,
                -kReviewInsetPixels, -kReviewInsetPixels);
            const QSize fitted = original.size().scaled(
                insetFace.size().toSize(), Qt::KeepAspectRatio);
            const QPointF offset(
                (canvasCenter.x() - contentCenter.x()) * kReviewOffsetGain *
                    fitted.width() / original.width(),
                (canvasCenter.y() - contentCenter.y()) * kReviewOffsetGain *
                    fitted.height() / original.height());
            const QRectF reviewPlacement(
                face.center().x() - fitted.width() / 2.0 + offset.x(),
                face.center().y() - fitted.height() / 2.0 + offset.y(),
                fitted.width(), fitted.height());
            if (!face.contains(reviewPlacement)) {
                *error = QStringLiteral("launcher placement exceeds rounded card face");
                m_images.clear();
                return;
            }
            // Full source image: no sourceRect, no hidden clipping from
            // viewport cropping. The existing rounded mask remains in force.
            painter.drawImage(reviewPlacement, original);
        } else {
            // ORIGINAL full-image fit remains the default. The optional
            // independently approved Terminal derivative is never reframed.
            const QSize fitted = original.size().scaled(
                face.size().toSize(), Qt::KeepAspectRatio);
            const QRectF placement(face.center().x() - fitted.width() / 2.0,
                                   face.center().y() - fitted.height() / 2.0,
                                   fitted.width(), fitted.height());
            painter.drawImage(placement, original);
        }
        painter.end();
        m_images.insert(id, rendered);
    }
}

bool RoundedDockIconProvider::allCornersClipped() const {
    if (!isValid())
        return false;
    for (const QImage &image : m_images) {
        if (image.width() != kCanvasPixels || image.height() != kCanvasPixels ||
            image.pixelColor(0, 0).alpha() != 0 ||
            image.pixelColor(kInsetPixels + 1, kInsetPixels + 1).alpha() != 0 ||
            image.pixelColor(kCanvasPixels - kInsetPixels - 2,
                             kInsetPixels + 1).alpha() != 0 ||
            image.pixelColor(kInsetPixels + 1,
                             kCanvasPixels - kInsetPixels - 2).alpha() != 0 ||
            image.pixelColor(kCanvasPixels - kInsetPixels - 2,
                             kCanvasPixels - kInsetPixels - 2).alpha() != 0 ||
            image.pixelColor(kCanvasPixels / 2, kCanvasPixels / 2).alpha() < 250)
            return false;
    }
    return true;
}

QImage RoundedDockIconProvider::requestImage(const QString &id, QSize *size,
                                             const QSize &requestedSize) {
    const QImage original = m_images.value(id.toLower());
    if (original.isNull()) {
        if (size)
            *size = QSize();
        return QImage(); // Missing approved icon never falls back to demo SVG.
    }
    if (size)
        *size = original.size();
    if (!requestedSize.isValid() ||
        requestedSize.width() > kMaxRequestPixels ||
        requestedSize.height() > kMaxRequestPixels)
        return original;
    return original.scaled(requestedSize, Qt::KeepAspectRatio,
                           Qt::SmoothTransformation);
}
