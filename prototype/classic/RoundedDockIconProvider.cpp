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

// Directly reused measured, source-specific gutters from the earlier
// isolated PR #109. This candidate is never the default renderer.
// The chosen user PNG masters remain byte-exact and unmodified.
const QHash<QString, int> kApprovedSourceTopGutters = {
    {QStringLiteral("browser"), 9},
    {QStringLiteral("mail"), 6},
    {QStringLiteral("files"), 2},
    {QStringLiteral("calendar"), 0},
    {QStringLiteral("photos"), 0},
    {QStringLiteral("music"), 5},
    {QStringLiteral("terminal"), 14},
    {QStringLiteral("settings"), 14},
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
            // Review candidate A from PR #109, applied to the SAME shared Qt
            // image provider used by BOTH the dock and searchable launcher.
            // The outer 168px rounded face never moves. The approved original
            // remains untouched; this is an in-memory square content sample.
            if (!kApprovedSourceTopGutters.contains(id)) {
                *error = QStringLiteral("unknown approved source icon for framing review");
                m_images.clear();
                return;
            }
            const int top = kApprovedSourceTopGutters.value(id);
            const int side = original.height() - top;
            if (top < 0 || top > 14 || side < 256 || original.width() < side) {
                *error = QStringLiteral("approved image framing dimensions invalid");
                m_images.clear();
                return;
            }
            const int left = (original.width() - side) / 2;
            const QRectF originalSample(left, top, side, side);
            painter.drawImage(face, original, originalSample);
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
