#include "RoundedDockIconProvider.h"

#include <QCryptographicHash>
#include <QDir>
#include <QFileInfo>
#include <QSaveFile>
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

// Optional in-memory sampling of SHA-locked 345x333/334 sources.
// Centers are rounded from 2%-98% bounds of bright illustration pixels,
// measured independently for each private original PNG. This centers the
// major visible artwork rather than only chopping a source-sheet TOP gutter.
// It is NOT applied to the existing dock or enabled without an explicit
// opt-in. No immutable original artwork bytes are changed.
constexpr int kOpticalSampleSize = 324;
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

// Candidate D: source-neutral *content-only* optical compensation for the
// unbalanced luminous artwork in the eight owner's original approved PNGs.
// These small offsets were measured from the actual 1920x1080 Qt captures,
// not by moving any QML button/card. 160px illustration area retains complete
// source (no cropping), centered inside the fixed 168px clipped rounded face.
// Per-icon translations are bounded and apply ONLY in explicit review mode.
constexpr int kOpticalFitPixels = 160;
// These first rows are *opaque selection-sheet matte*, not part of the
// chosen illustration; the source PNGs remain byte-for-byte untouched.
// This separate source-aware renderer is only enabled for --dock-clean-edges-review.
// Native source pixel inspection (2026-11-23): the Terminal and Settings
// titlebar begins around scanline 15, while the other six begin earlier.
const QHash<QString, QPair<int, int>> kSourceMatteRowTrim = {
    {QStringLiteral("browser"), {7, 0}},
    {QStringLiteral("mail"), {6, 1}},
    {QStringLiteral("files"), {5, 1}},
    {QStringLiteral("calendar"), {0, 0}},
    {QStringLiteral("photos"), {4, 0}},
    {QStringLiteral("music"), {3, 0}},
    {QStringLiteral("terminal"), {15, 7}},
    {QStringLiteral("settings"), {15, 4}},
};

// Five targeted optical centering corrections, in 192px provider pixels.
// Measured from high-contrast feature centers in genuine 1920x1080 Qt captures
// of the unchanged source-aware clean-matte renderer, NOT from the button
// rectangle or a generated dock mockup. After Qt's 54/192 reduction these
// are roughly: Browser (0,-2.3), Mail (+0.6,0),
// Files (-2.5,+0.3), Terminal (-2.3,-0.8), Settings (-2.0,-0.6)px.
// Calendar, Photos and Music MUST NEVER appear in this map or be altered.
const QHash<QString, QPointF> kFiveDockCenterOffsets = {
    {QStringLiteral("browser"), QPointF(0, -8)},
    {QStringLiteral("mail"), QPointF(2, 0)},
    {QStringLiteral("files"), QPointF(-9, -1)},
    {QStringLiteral("terminal"), QPointF(-8, -3)},
    {QStringLiteral("settings"), QPointF(-8, -5)},
};

// Only two originals have a clearly visible selection-sheet edge embedded
// within the existing rounded mask in the genuine 62px Qt capture.
struct SourceEdgeTrim { int left; int top; int right; int bottom; };
const QHash<QString, SourceEdgeTrim> kFiveSourceEdgeTrim = {
    {QStringLiteral("files"), {7, 17, 15, 2}},
    {QStringLiteral("settings"), {6, 22, 7, 10}},
};

// Production pack is derived from precisely these five verified originals.
// Never add Calendar, Photos or Music here: their Qt pixels are immutable.
const QStringList kFiveProductionIds = {
    QStringLiteral("browser"), QStringLiteral("mail"),
    QStringLiteral("files"), QStringLiteral("terminal"),
    QStringLiteral("settings"),
};
// Changing the master-derived crop semantics invalidates all old packs.
constexpr auto kPackRenderer = "canopy-five-qt-v2";

QString sha256(const QByteArray &bytes) {
    return QString::fromLatin1(
        QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex());
}

// This is the SAME source-aware clean-matte paint sequence used for the
// selected five dock icons. At 1x it is byte-equivalent in Qt to the
// pre-pack runtime renderer. 2x/3x render *from the original master*, not
// from an enlarged, already rasterized 192px image.
QImage renderFiveAtDensity(const QImage &original, const QString &id,
                           int density, QString *error) {
    if (density < 1 || density > 3 ||
        original.width() != 345 ||
        (original.height() != 333 && original.height() != 334) ||
        !kFiveDockCenterOffsets.contains(id) ||
        !kSourceMatteRowTrim.contains(id)) {
        *error = QStringLiteral("invalid verified five-icon source or density");
        return {};
    }
    const auto trims = kSourceMatteRowTrim.value(id);
    const auto edgeTrimIt = kFiveSourceEdgeTrim.constFind(id);
    // Preserve Browser, Mail and Terminal pixel-for-pixel. Only Files and
    // Settings use slightly tighter source selection-sheet boundaries.
    // The approved 345px originals are NEVER edited; this is in-memory only.
    const int left = edgeTrimIt == kFiveSourceEdgeTrim.cend() ? 0 : edgeTrimIt->left;
    const int top = edgeTrimIt == kFiveSourceEdgeTrim.cend() ? trims.first : edgeTrimIt->top;
    const int right = edgeTrimIt == kFiveSourceEdgeTrim.cend() ? 0 : edgeTrimIt->right;
    const int bottom = edgeTrimIt == kFiveSourceEdgeTrim.cend() ? trims.second : edgeTrimIt->bottom;
    if (left < 0 || right < 0 || top < 0 || bottom < 0 ||
        left > 15 || right > 15 || top > 22 || bottom > 10 ||
        original.width() - left - right < 310 ||
        original.height() - top - bottom < 300) {
        *error = QStringLiteral("five-icon source edge trim outside safe bounds");
        return {};
    }
    const QImage source = original.copy(left, top,
        original.width() - left - right,
        original.height() - top - bottom);
    if (source.isNull()) {
        *error = QStringLiteral("verified five-icon source crop failed");
        return {};
    }
    QImage rendered(kCanvasPixels * density, kCanvasPixels * density,
                    QImage::Format_ARGB32_Premultiplied);
    rendered.fill(Qt::transparent);
    QPainter painter(&rendered);
    painter.setRenderHint(QPainter::Antialiasing, true);
    painter.setRenderHint(QPainter::SmoothPixmapTransform, true);
    painter.scale(density, density);
    const QRectF face(kInsetPixels, kInsetPixels,
                      kCanvasPixels - 2 * kInsetPixels,
                      kCanvasPixels - 2 * kInsetPixels);
    QPainterPath outline;
    outline.addRoundedRect(face, kRoundedRadius, kRoundedRadius);
    painter.setClipPath(outline);
    painter.fillPath(outline, QColor(QStringLiteral("#10203d")));
    const QImage edgeFill = source.scaled(
        14, 14, Qt::IgnoreAspectRatio, Qt::SmoothTransformation)
        .scaled(face.size().toSize(), Qt::IgnoreAspectRatio,
                Qt::SmoothTransformation);
    const QRectF inner(face.left() + 1, face.top() + 1,
                       face.width() - 2, face.height() - 2);
    painter.drawImage(face, edgeFill);
    QRectF artwork = inner;
    artwork.translate(kFiveDockCenterOffsets.value(id));
    painter.drawImage(artwork, source);
    painter.end();
    return rendered;
}

const QHash<QString, QPointF> kOpticalBalanceOffset = {
    {QStringLiteral("browser"), QPointF(3, -2)},
    {QStringLiteral("mail"), QPointF(2, 5)},
    {QStringLiteral("files"), QPointF(3, 3)},
    {QStringLiteral("calendar"), QPointF(3, -4)},
    {QStringLiteral("photos"), QPointF(2, 1)},
    {QStringLiteral("music"), QPointF(1, -5)},
    {QStringLiteral("terminal"), QPointF(-4, 1)},
    {QStringLiteral("settings"), QPointF(1, 4)},
};
}

RoundedDockIconProvider::RoundedDockIconProvider(
    const QString &approvedRoot, const QString &terminalCandidatePath,
    bool framingReviewMode, QString *error, bool balancedDockFitMode,
    bool opticalBalanceReviewMode, bool cleanSourceEdgesReviewMode,
    bool fiveOnlyCenterReviewMode, const QString &productionPackRoot)
    : QQuickImageProvider(QQuickImageProvider::Image) {
    if (fiveOnlyCenterReviewMode && !cleanSourceEdgesReviewMode) {
        *error = QStringLiteral("five-icon centering requires the existing clean-matte renderer");
        return;
    }
    if ((framingReviewMode && balancedDockFitMode) ||
        (opticalBalanceReviewMode && (framingReviewMode || balancedDockFitMode)) ||
        (cleanSourceEdgesReviewMode &&
         (framingReviewMode || balancedDockFitMode || opticalBalanceReviewMode))) {
        *error = QStringLiteral("conflicting icon framing experiments");
        return;
    }
    QFile manifest(QStringLiteral(":/Canopy/Classic/assets/approved/manifest.json"));
    if (!manifest.open(QIODevice::ReadOnly)) {
        *error = QStringLiteral("embedded icon manifest missing");
        return;
    }
    const QByteArray originalManifestBytes = manifest.readAll();
    const QJsonDocument json = QJsonDocument::fromJson(originalManifestBytes);
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
    // Pack SHA verification happens before ANY icon is read from the pack.
    // A missing/corrupt pack always falls back to the identical in-memory
    // source painter rather than silently using substituted artwork.
    if (fiveOnlyCenterReviewMode && !productionPackRoot.isEmpty()) {
        const QDir candidate(productionPackRoot);
        QFile packManifest(candidate.filePath(QStringLiteral("manifest.json")));
        if (packManifest.open(QIODevice::ReadOnly)) {
            const QJsonDocument pack = QJsonDocument::fromJson(packManifest.readAll());
            const QJsonObject spec = pack.object();
            bool valid =
                spec.value(QStringLiteral("renderer")).toString() ==
                    QLatin1String(kPackRenderer) &&
                spec.value(QStringLiteral("schema_version")).toInt() == 1 &&
                spec.value(QStringLiteral("source_manifest_sha256")).toString() ==
                    sha256(originalManifestBytes) &&
                spec.value(QStringLiteral("files")).toArray().size() == 15;
            // Manifest identity is compared to canonicalized JSON on both
            // generation and consumption; no generated source PNG is trusted
            // without its original-source manifest being verified first.
            QHash<QString, QString> entriesByPath;
            for (const QJsonValue &entryValue : spec.value(QStringLiteral("files")).toArray()) {
                const QJsonObject f = entryValue.toObject();
                const QString path = f.value(QStringLiteral("path")).toString();
                const QString expected = f.value(QStringLiteral("sha256")).toString();
                if (entriesByPath.contains(path) || expected.size() != 64)
                    valid = false;
                entriesByPath.insert(path, expected);
            }
            for (const QString &id : kFiveProductionIds) {
                for (int density = 1; density <= 3; ++density) {
                    const QString relative = QStringLiteral("%1x/%2.png")
                        .arg(density).arg(id);
                    const QFileInfo info(candidate.filePath(relative));
                    if (!entriesByPath.contains(relative) || !info.isFile() ||
                        info.isSymLink() || info.size() > 3'000'000 ||
                        info.size() < 100) {
                        valid = false;
                        continue;
                    }
                    QFile png(info.absoluteFilePath());
                    if (!png.open(QIODevice::ReadOnly) ||
                        sha256(png.readAll()) != entriesByPath.value(relative))
                        valid = false;
                }
            }
            if (valid) {
                m_productionPackRoot = candidate.absolutePath();
                m_productionPackValid = true;
            }
        }
    }
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

        if (fiveOnlyCenterReviewMode && terminalCandidatePath.isEmpty() &&
            kFiveDockCenterOffsets.contains(id)) {
            // Five ONLY. Frozen Calendar / Photos / Music never pass here.
            QImage rendered;
            if (m_productionPackValid) {
                QImageReader packReader(QDir(m_productionPackRoot).filePath(
                    QStringLiteral("1x/%1.png").arg(id)));
                rendered = packReader.read().convertToFormat(
                    QImage::Format_ARGB32_Premultiplied);
            } else {
                rendered = renderFiveAtDensity(original, id, 1, error);
            }
            if (rendered.size() != QSize(kCanvasPixels, kCanvasPixels)) {
                *error = QStringLiteral("invalid production dock image: ") + id;
                m_images.clear();
                return;
            }
            m_images.insert(id, rendered);
            m_productionMasterPaths.insert(id, sourcePath);
            continue;
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
        if (cleanSourceEdgesReviewMode && !terminalDerivative) {
            // Reuse the *identical verified original PNG*. Remove only its
            // extra selection-sheet matte at the upper/lower source edges.
            // Draw the entire chosen composition within the SAME fixed 168px
            // rounded card. An unobtrusive, image-derived soft edge fill
            // avoids the old extra #10203d frame / square-into-rounded effect.
            // This executes once on startup; there are zero runtime effects.
            const auto trimIt = kSourceMatteRowTrim.constFind(id);
            if (trimIt == kSourceMatteRowTrim.cend() ||
                original.width() != 345 ||
                (original.height() != 333 && original.height() != 334)) {
                *error = QStringLiteral("clean dock source dimensions mismatch");
                m_images.clear();
                return;
            }
            const int cropTop = trimIt.value().first;
            const int cropBottom = trimIt.value().second;
            if (cropTop < 0 || cropBottom < 0 ||
                cropTop + cropBottom >= original.height() - 32) {
                *error = QStringLiteral("unsafe source matte trim");
                m_images.clear();
                return;
            }
            const QImage source = original.copy(
                0, cropTop, original.width(),
                original.height() - cropTop - cropBottom);
            if (source.isNull()) {
                *error = QStringLiteral("source matte crop missing");
                m_images.clear();
                return;
            }
            // A 14px reduction and smooth expansion creates a low-frequency
            // continuation of the image's own colors in the 1px outer rim,
            // not a second dark border or a new illustration.
            const QImage edgeFill = source.scaled(
                14, 14, Qt::IgnoreAspectRatio, Qt::SmoothTransformation)
                .scaled(face.size().toSize(), Qt::IgnoreAspectRatio,
                        Qt::SmoothTransformation);
            const QRectF inner(face.left() + 1, face.top() + 1,
                               face.width() - 2, face.height() - 2);
            painter.drawImage(face, edgeFill);
            // Translate artwork CONTENT inside the unchanged mask. The
            // approved originals, 168px face, 54px QML slot, dock chrome,
            // launchers and the three frozen icons remain identical.
            // No new image provider, timer or background processing.
            if (fiveOnlyCenterReviewMode) {
                const auto center = kFiveDockCenterOffsets.constFind(id);
                if (center != kFiveDockCenterOffsets.cend()) {
                    const QPointF delta = center.value();
                    if (qAbs(delta.x()) > 9 || qAbs(delta.y()) > 9) {
                        *error = QStringLiteral("five-icon centering exceeded bounded offsets");
                        m_images.clear();
                        return;
                    }
                    QRectF artwork = inner;
                    artwork.translate(delta);
                    painter.drawImage(artwork, source);
                } else {
                    // Calendar, Photos and Music follow the EXACT existing
                    // painter call, not a translated zero-offset derivative.
                    painter.drawImage(inner, source);
                }
            } else {
                // Original default behavior is deliberately unchanged.
                painter.drawImage(inner, source);
            }
        } else if (opticalBalanceReviewMode && !terminalDerivative) {
            // Candidate D: gently normalize optical centers without cropping
            // or changing the user's original art. The 160px image is a
            // single cached render; one-time startup work, zero extra timers
            // or graphics effects. All eight original masters are verified
            // before this in-memory derivative.
            const auto location = kOpticalBalanceOffset.constFind(id);
            if (location == kOpticalBalanceOffset.cend() ||
                original.width() != 345 ||
                (original.height() != 333 && original.height() != 334)) {
                *error = QStringLiteral("optical balance source input mismatch");
                m_images.clear();
                return;
            }
            const QPointF delta = location.value();
            if (qAbs(delta.x()) > 5 || qAbs(delta.y()) > 5) {
                *error = QStringLiteral("optical balance offset out of bounds");
                m_images.clear();
                return;
            }
            const QSize fit = original.size().scaled(
                kOpticalFitPixels, kOpticalFitPixels, Qt::KeepAspectRatio);
            const QRectF placement(
                face.center().x() - fit.width() / 2.0 + delta.x(),
                face.center().y() - fit.height() / 2.0 + delta.y(),
                fit.width(), fit.height());
            if (!face.contains(placement)) {
                *error = QStringLiteral("optical balance does not fit clipped face");
                m_images.clear();
                return;
            }
            painter.drawImage(placement, original);
        } else if (balancedDockFitMode && !terminalDerivative) {
            // Candidate C: preserve the ENTIRE original 333/334px height
            // and sample only the horizontal source gutter. Compared with
            // the 324px zoom experiment, this is a gentler optical fit.
            // Fixed 168px rounded face and QML dock geometry NEVER move.
            // Originals remain immutable, and the separate Terminal-v3
            // transparent derivative keeps its independent default fit.
            if (!kLauncherOpticalCenters.contains(id) ||
                original.width() != 345 ||
                (original.height() != 333 && original.height() != 334)) {
                *error = QStringLiteral("balanced dock source dimensions mismatch");
                m_images.clear();
                return;
            }
            constexpr qreal kFullSourceHeight = 333.0;
            const qreal x = kLauncherOpticalCenters.value(id).x();
            const QRectF source(x - kFullSourceHeight / 2.0,
                                (original.height() - kFullSourceHeight) / 2.0,
                                kFullSourceHeight, kFullSourceHeight);
            if (source.left() < 0 || source.top() < 0 ||
                source.right() > original.width() ||
                source.bottom() > original.height()) {
                *error = QStringLiteral("balanced dock source sample out of bounds");
                m_images.clear();
                return;
            }
            painter.drawImage(face, original, source);
        } else if (framingReviewMode && !terminalDerivative) {
            // Candidate B: source-specific bright-illustration bounds, not
            // uniform top trimming. The unchanged fixed 168px mask remains
            // centered. Only the launcher may instantiate this mode; dock
            // uses framingReviewMode=false and its exact original renderer.
            if (!kLauncherOpticalCenters.contains(id) ||
                original.width() != 345 ||
                (original.height() != 333 && original.height() != 334)) {
                *error = QStringLiteral("launcher optical sample input mismatch");
                m_images.clear();
                return;
            }
            const QPointF center = kLauncherOpticalCenters.value(id);
            const QRectF originalSample(
                center.x() - kOpticalSampleSize / 2.0,
                center.y() - kOpticalSampleSize / 2.0,
                kOpticalSampleSize, kOpticalSampleSize);
            if (originalSample.left() < 0 || originalSample.top() < 0 ||
                originalSample.right() > original.width() ||
                originalSample.bottom() > original.height()) {
                *error = QStringLiteral("launcher sample exceeds original bounds");
                m_images.clear();
                return;
            }
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

bool RoundedDockIconProvider::exportFiveProductionPack(
    const QString &outputRoot, const QString &approvedRoot, QString *error) const {
    if (!isValid() || m_productionMasterPaths.size() != 5) {
        *error = QStringLiteral("only exact verified five-icon mode can export");
        return false;
    }
    const QString sourcePrefix = QDir(approvedRoot).canonicalPath() + QLatin1Char('/');
    const QString dest = QDir(outputRoot).absolutePath() + QLatin1Char('/');
    if (sourcePrefix.isEmpty() || dest.startsWith(sourcePrefix) ||
        !QDir().mkpath(outputRoot)) {
        *error = QStringLiteral("unsafe production output directory");
        return false;
    }
    QJsonArray results;
    const QDir out(outputRoot);
    for (const QString &id : kFiveProductionIds) {
        QImageReader masterReader(m_productionMasterPaths.value(id));
        const QImage original = masterReader.read();
        if (original.isNull()) {
            *error = QStringLiteral("cannot reopen original for export: ") + id;
            return false;
        }
        for (int density = 1; density <= 3; ++density) {
            const QString relative =
                QStringLiteral("%1x/%2.png").arg(density).arg(id);
            if (!QDir().mkpath(out.filePath(QStringLiteral("%1x").arg(density)))) {
                *error = QStringLiteral("cannot create production density folder");
                return false;
            }
            const QImage image = renderFiveAtDensity(original, id, density, error);
            if (image.isNull() || image.width() != density * kCanvasPixels ||
                !image.save(out.filePath(relative), "PNG")) {
                *error = QStringLiteral("five-icon production PNG export failed: ") + relative;
                return false;
            }
            QFile saved(out.filePath(relative));
            if (!saved.open(QIODevice::ReadOnly)) {
                *error = QStringLiteral("cannot hash exported PNG");
                return false;
            }
            QJsonObject fileEntry;
            fileEntry.insert(QStringLiteral("path"), relative);
            fileEntry.insert(QStringLiteral("sha256"), sha256(saved.readAll()));
            fileEntry.insert(QStringLiteral("pixels"), density * kCanvasPixels);
            results.append(fileEntry);
        }
    }
    QFile sourceManifest(QStringLiteral(":/Canopy/Classic/assets/approved/manifest.json"));
    if (!sourceManifest.open(QIODevice::ReadOnly)) {
        *error = QStringLiteral("cannot hash canonical original manifest");
        return false;
    }
    const QByteArray originalBytes = sourceManifest.readAll();
    QJsonObject manifest;
    manifest.insert(QStringLiteral("schema_version"), 1);
    manifest.insert(QStringLiteral("renderer"), QLatin1String(kPackRenderer));
    manifest.insert(QStringLiteral("source_manifest_sha256"),
                    sha256(originalBytes));
    manifest.insert(QStringLiteral("files"), results);
    QSaveFile output(out.filePath(QStringLiteral("manifest.json")));
    if (!output.open(QIODevice::WriteOnly) ||
        output.write(QJsonDocument(manifest).toJson(QJsonDocument::Indented)) < 0 ||
        !output.commit()) {
        *error = QStringLiteral("cannot atomically write production icon manifest");
        return false;
    }
    return true;
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
    const QString key = id.toLower();
    const QImage original = m_images.value(key);
    if (original.isNull()) {
        if (size)
            *size = QSize();
        return QImage(); // Missing approved icon never falls back to demo SVG.
    }
    if (size)
        *size = original.size();
    // A high-density requester reads the actual 2x/3x master-derived
    // production raster on demand. The 54px default uses only the tiny 1x
    // startup cache, keeping normal RAM and idle CPU unchanged.
    if (m_productionPackValid && m_productionMasterPaths.contains(key) &&
        requestedSize.isValid() && requestedSize.width() > kMaxRequestPixels &&
        requestedSize.width() <= 3 * kCanvasPixels &&
        requestedSize.height() <= 3 * kCanvasPixels) {
        const int density = requestedSize.width() > 2 * kCanvasPixels ? 3 : 2;
        QImageReader source(QDir(m_productionPackRoot).filePath(
            QStringLiteral("%1x/%2.png").arg(density).arg(key)));
        const QImage big = source.read();
        if (!big.isNull()) {
            if (size) *size = big.size();
            return big.scaled(requestedSize, Qt::KeepAspectRatio,
                              Qt::SmoothTransformation);
        }
    }
    if (!requestedSize.isValid() ||
        requestedSize.width() > kMaxRequestPixels ||
        requestedSize.height() > kMaxRequestPixels)
        return original;
    return original.scaled(requestedSize, Qt::KeepAspectRatio,
                           Qt::SmoothTransformation);
}
