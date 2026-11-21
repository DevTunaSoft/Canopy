#include "RoundedDockIconProvider.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QQuickItem>
#include <QtMath>
#include <QDebug>
#include <QTimer>
#include <QCoreApplication>
#include <QImage>
#include <QImageReader>
#include <QStringList>
#include <QRegularExpression>
#include <QSet>
#include <QVector>
#include <QQmlContext>
#include <QCryptographicHash>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QUrl>

// A Repeater can give its delegates QObject owners different from their
// visual parents. Traverse the actual QQuickItem scene tree for UI assertions.
static QQuickItem *findVisualItem(QQuickItem *parent, const QString &name) {
    if (!parent)
        return nullptr;
    if (parent->objectName() == name)
        return parent;
    for (QQuickItem *child : parent->childItems()) {
        if (auto *match = findVisualItem(child, name))
            return match;
    }
    return nullptr;
}

// Find the named dock control in the *visual* tree, including Repeater items.
static QQuickItem *findDockTile(QQuickItem *parent, const QString &iconName) {
    if (!parent)
        return nullptr;
    if (parent->objectName() == QStringLiteral("canopyDockTile") &&
        parent->property("iconName").toString() == iconName)
        return parent;
    for (QQuickItem *child : parent->childItems()) {
        if (auto *match = findDockTile(child, iconName))
            return match;
    }
    return nullptr;
}

static int countReadyFolderTiles(QQuickItem *parent) {
    if (!parent)
        return 0;
    int ready = parent->objectName() == QStringLiteral("canopyFolderTile")
                && parent->property("imageReady").toBool() ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        ready += countReadyFolderTiles(child);
    return ready;
}

static int countReadyDockTiles(QQuickItem *parent) {
    if (!parent)
        return 0;
    int ready = parent->objectName() == QStringLiteral("canopyDockTile")
                && parent->property("iconReady").toBool() ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        ready += countReadyDockTiles(child);
    return ready;
}

static int countVisualItems(QQuickItem *parent, const QString &objectName) {
    if (!parent)
        return 0;
    int count = parent->objectName() == objectName ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        count += countVisualItems(child, objectName);
    return count;
}

// An approved visual is never loaded from a guessed path or a replacement
// file. The manifest is source-controlled, and all nine external PNGs must
// match the exact source bytes before Qt is allowed to open the scene.
static bool verifyExactArtwork(const QString &dirPath, bool requireWave, QString *error) {
    const QDir root(dirPath);
    const QString canonicalRoot = root.canonicalPath();
    if (canonicalRoot.isEmpty() || QFileInfo(dirPath).isSymLink()) {
        *error = QStringLiteral("approved-art directory is missing or is a symlink");
        return false;
    }
    QFile manifest(QStringLiteral(":/Canopy/Classic/assets/approved/manifest.json"));
    if (!manifest.open(QIODevice::ReadOnly)) {
        *error = QStringLiteral("embedded approved-art manifest missing");
        return false;
    }
    QJsonParseError parseError;
    const QJsonDocument json = QJsonDocument::fromJson(manifest.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !json.isObject()) {
        *error = QStringLiteral("approved-art manifest failed to parse");
        return false;
    }
    const QJsonObject config = json.object();
    const QJsonArray icons = config.value(QStringLiteral("icons")).toArray();
    const QJsonObject wallpaper = config.value(QStringLiteral("wallpaper")).toObject();
    if (config.value(QStringLiteral("schema_version")).toInt() != 1 ||
        icons.size() != 8 || wallpaper.isEmpty()) {
        *error = QStringLiteral("approved manifest must contain exactly eight icons and one wallpaper");
        return false;
    }
    QSet<QString> checkedPaths;
    auto verify = [&](const QJsonObject &item) -> bool {
        const QString relative = item.value(QStringLiteral("path")).toString();
        const QString sha = item.value(QStringLiteral("sha256")).toString();
        if (relative.isEmpty() || !relative.endsWith(QStringLiteral(".png")) ||
            relative.startsWith(QLatin1Char('/')) ||
            relative.contains(QLatin1Char('\\')) ||
            relative.split(QLatin1Char('/')).contains(QStringLiteral("..")) ||
            checkedPaths.contains(relative) || sha.size() != 64) {
            *error = QStringLiteral("invalid or duplicate approved-art manifest entry");
            return false;
        }
        checkedPaths.insert(relative);
        const QFileInfo asset(root.filePath(relative));
        if (!asset.exists() || !asset.isFile() || asset.isSymLink() ||
            asset.size() > 12'000'000 ||
            !asset.canonicalFilePath().startsWith(canonicalRoot + QLatin1Char('/'))) {
            *error = QStringLiteral("approved image is missing, unsafe or outside approved directory: ") + relative;
            return false;
        }
        QFile file(asset.absoluteFilePath());
        if (!file.open(QIODevice::ReadOnly)) {
            *error = QStringLiteral("cannot read approved art: ") + relative;
            return false;
        }
        const QByteArray digest = QCryptographicHash::hash(
            file.readAll(), QCryptographicHash::Sha256).toHex();
        if (digest != sha.toLatin1()) {
            *error = QStringLiteral("SHA-256 mismatch, refusing substitute: ") + relative;
            return false;
        }
        return true;
    };
    for (const QJsonValue &item : icons) {
        if (!item.isObject() || !verify(item.toObject()))
            return false;
    }
    if ((requireWave && !verify(wallpaper)) ||
        checkedPaths.size() != (requireWave ? 9 : 8)) {
        if (error->isEmpty())
            *error = QStringLiteral("incomplete approved-art set");
        return false;
    }
    return true;
}

// Local photo only; never download artwork, follow symlinks, or decode an
// unbounded image. QImageReader checks headers without allocating a bitmap.
static bool verifyLandscapeWallpaper(const QString &filePath,
                                     QString *canonicalPath, QString *error) {
    const QFileInfo file(filePath);
    if (!file.exists() || !file.isFile() || file.isSymLink() ||
        file.size() <= 0 || file.size() > 24'000'000) {
        *error = QStringLiteral("wallpaper must be a regular local image (up to 24 MB)");
        return false;
    }
    const QString extension = file.suffix().toLower();
    if (extension != QStringLiteral("png") &&
        extension != QStringLiteral("jpg") &&
        extension != QStringLiteral("jpeg")) {
        *error = QStringLiteral("wallpaper must be PNG or JPEG");
        return false;
    }
    const QString canonical = file.canonicalFilePath();
    if (canonical.isEmpty()) {
        *error = QStringLiteral("wallpaper path is invalid");
        return false;
    }
    QImageReader reader(canonical);
    const QByteArray format = reader.format().toLower();
    if (!reader.canRead() ||
        (format != "png" && format != "jpeg" && format != "jpg")) {
        *error = QStringLiteral("wallpaper content is not a readable PNG/JPEG");
        return false;
    }
    const QSize size = reader.size();
    if (!size.isValid() || size.width() < 1920 || size.height() < 1080 ||
        size.width() > 8192 || size.height() > 8192 ||
        qint64(size.width()) * size.height() > 32'000'000 ||
        double(size.width()) / size.height() < 1.45 ||
        double(size.width()) / size.height() > 2.15) {
        *error = QStringLiteral("wallpaper must be landscape, at least 1920x1080, at most 32 megapixels");
        return false;
    }
    *canonicalPath = canonical;
    return true;
}

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationDisplayName(QStringLiteral("Canopy Classic Spike"));
    const QStringList args = QCoreApplication::arguments();
    const int approvedIndex = args.indexOf(QStringLiteral("--approved-art-dir"));
    const bool approvedMode = approvedIndex >= 0;
    const bool requireApproved = args.contains(QStringLiteral("--self-test-approved"));
    const int landscapeIndex = args.indexOf(QStringLiteral("--landscape-wallpaper"));
    const bool landscapeMode = landscapeIndex >= 0;
    QString landscapePath;
    if (landscapeMode) {
        if (landscapeIndex + 1 >= args.size() ||
            args.at(landscapeIndex + 1).startsWith(QLatin1Char('-'))) {
            qCritical() << "LANDSCAPE_WALLPAPER_FAIL: missing --landscape-wallpaper PATH";
            return 2;
        }
        QString error;
        if (!verifyLandscapeWallpaper(args.at(landscapeIndex + 1),
                                      &landscapePath, &error)) {
            qCritical().noquote() << "LANDSCAPE_WALLPAPER_FAIL:" << error;
            return 3;
        }
        qInfo() << "CANOPY_LANDSCAPE_WALLPAPER_VERIFIED: local PNG/JPEG";
    }
    if (requireApproved && !approvedMode) {
        qCritical() << "APPROVED_ART_FAIL: --self-test-approved requires --approved-art-dir";
        return 2;
    }
    QString approvedRoot;
    if (approvedMode) {
        if (approvedIndex + 1 >= args.size() || args.at(approvedIndex + 1).startsWith(QLatin1Char('-'))) {
            qCritical() << "APPROVED_ART_FAIL: missing --approved-art-dir PATH";
            return 2;
        }
        const QString requested = args.at(approvedIndex + 1);
        QString error;
        if (!verifyExactArtwork(requested, !landscapeMode, &error)) {
            qCritical().noquote() << "APPROVED_ART_FAIL:" << error;
            return 3;
        }
        approvedRoot = QDir(requested).canonicalPath();
        qInfo() << (landscapeMode ?
            "CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons; landscape wallpaper separately checked" :
            "CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave");
    }
    QQmlApplicationEngine engine;
    if (approvedMode) {
        // Source PNGs were SHA-verified above; transform copies IN MEMORY
        // only. The files and their immutable manifest remain unchanged.
        QString roundedError;
        auto *roundedIcons = new RoundedDockIconProvider(approvedRoot, &roundedError);
        if (!roundedIcons->isValid() || !roundedIcons->allCornersClipped()) {
            qCritical().noquote() << "APPROVED_ART_FAIL: rounded dock rendering:"
                                   << roundedError;
            delete roundedIcons;
            return 3;
        }
        engine.addImageProvider(QStringLiteral("canopy-dock"), roundedIcons);
        qInfo() << "CANOPY_ROUNDED_DOCK_VERIFIED: eight original icons, padded, alpha-clipped";
    }
    engine.rootContext()->setContextProperty(QStringLiteral("canopyApprovedMode"), approvedMode);
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyLandscapeWallpaperUrl"),
        landscapeMode ? QUrl::fromLocalFile(landscapePath).toString() : QString());
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyApprovedIconBase"),
        approvedMode ? QUrl::fromLocalFile(approvedRoot + QStringLiteral("/icons/")).toString()
                     : QString());
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyApprovedWallpaperUrl"),
        approvedMode ? QUrl::fromLocalFile(
            approvedRoot + QStringLiteral("/wallpaper/canopy-wave-preview.png")).toString()
                     : QString());
    engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")));
    if (engine.rootObjects().isEmpty())
        return 1;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window || !window->isVisible()) {
        qCritical() << "Canopy Classic: QML root did not create a visible window";
        return 1;
    }
    qInfo() << "CANOPY_CLASSIC_WINDOW_READY";
    const int sizeIndex = args.indexOf(QStringLiteral("--self-test-size"));
    if (sizeIndex >= 0) {
        if (sizeIndex + 1 >= args.size()) {
            qCritical() << "Missing --self-test-size WIDTHxHEIGHT";
            return 2;
        }
        const auto match = QRegularExpression(QStringLiteral("^(\\d+)x(\\d+)$")).match(args.at(sizeIndex + 1));
        if (!match.hasMatch()) {
            qCritical() << "Invalid --self-test-size value";
            return 2;
        }
        const int width = match.captured(1).toInt();
        const int height = match.captured(2).toInt();
        if (width < 720 || height < 480 || width > 3840 || height > 2160) {
            qCritical() << "Self-test size outside supported test range";
            return 2;
        }
        window->resize(width, height);
    }
    const int screenshotIndex = args.indexOf(QStringLiteral("--self-test-screenshot"));
    if (screenshotIndex >= 0) {
        if (screenshotIndex + 1 >= args.size()) {
            qCritical() << "Missing screenshot output path";
            return 2;
        }
        const QString screenshotPath = args.at(screenshotIndex + 1);
        QTimer::singleShot(1000, window, [window, screenshotPath, approvedMode, landscapeMode]() {
            auto *bar = window->findChild<QQuickItem *>(QStringLiteral("canopyTopBar"));
            auto *dock = window->findChild<QQuickItem *>(QStringLiteral("canopyDock"));
            auto *launcher = window->findChild<QQuickItem *>(QStringLiteral("canopyLauncher"));
            auto *preview = window->findChild<QQuickItem *>(QStringLiteral("canopyPreviewWindow"));
            auto *wallpaper = window->findChild<QQuickItem *>(QStringLiteral("canopyWallpaper"));
            if (!bar || !dock || !launcher || !preview || !wallpaper) {
                qCritical() << "SELF_TEST_FAIL: missing required desktop chrome";
                QCoreApplication::exit(1);
                return;
            }
            const QPointF barOrigin = bar->mapToItem(window->contentItem(), QPointF(0, 0));
            const QPointF dockOrigin = dock->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool barFits = qAbs(barOrigin.x()) <= 2 && qAbs(barOrigin.y()) <= 2
                && qAbs(bar->width() - window->width()) <= 2 && bar->height() >= 30;
            const bool dockFits = dockOrigin.x() >= 0 && dockOrigin.y() >= bar->height()
                && dockOrigin.x() + dock->width() <= window->width() + 1
                && dockOrigin.y() + dock->height() <= window->height() + 1
                && qAbs(dockOrigin.x() + dock->width() / 2 - window->width() / 2) <= 2;
            if (!launcher->property("imageReady").toBool()) {
                qCritical() << "SELF_TEST_FAIL: original Canopy launcher icon did not load";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: original Canopy penguin launcher loaded";
            const QPointF launcherOrigin = launcher->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool launcherFits = launcher->width() >= 24 && launcher->height() >= 28
                && launcherOrigin.x() >= 0 && launcherOrigin.y() >= 0
                && launcherOrigin.x() + launcher->width() <= window->width()
                && launcherOrigin.y() + launcher->height() <= bar->height() + 1;
            if (!barFits || !dockFits || !launcherFits) {
                qCritical() << "SELF_TEST_FAIL: desktop chrome geometry invalid"
                            << "window" << window->size() << "bar" << barOrigin << bar->size()
                            << "dock" << dockOrigin << dock->size()
                            << "launcher" << launcherOrigin << launcher->size();
                QCoreApplication::exit(1);
                return;
            }
            const QPointF previewOrigin = preview->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool previewFits = previewOrigin.x() >= 0
                && previewOrigin.y() >= bar->height() - 1
                && previewOrigin.x() + preview->width() <= window->width() + 1
                && previewOrigin.y() + preview->height() <= dockOrigin.y() - 12
                && preview->width() >= 480 && preview->height() >= 250;
            if (!previewFits) {
                qCritical() << "SELF_TEST_FAIL: preview overlaps desktop chrome or is too small"
                            << "window" << window->size() << "preview" << previewOrigin
                            << preview->size() << "dock" << dockOrigin << dock->size();
                QCoreApplication::exit(1);
                return;
            }
            const int dockTileCount = countVisualItems(dock, QStringLiteral("canopyDockTile"));
            if (!wallpaper->property("imageReady").toBool()) {
                if (landscapeMode)
                    qCritical() << "SELF_TEST_FAIL: validated landscape wallpaper did not decode";
                else
                    qCritical() << "SELF_TEST_FAIL: Blue Current wallpaper image did not load"
                                << "check Qt SVG plugin and embedded artwork";
                QCoreApplication::exit(1);
                return;
            }
            if (landscapeMode)
                qInfo() << "SELF_TEST_PASS: validated custom landscape wallpaper loaded";
            else
                qInfo() << "SELF_TEST_PASS: original SVG wallpaper image loaded";
            const QPointF wallpaperOrigin = wallpaper->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool wallpaperFits = qAbs(wallpaperOrigin.x()) <= 1
                && qAbs(wallpaperOrigin.y()) <= 1
                && qAbs(wallpaper->width() - window->width()) <= 1
                && qAbs(wallpaper->height() - window->height()) <= 1;
            const int iconReadyCount = countReadyDockTiles(dock);
            if (iconReadyCount != (approvedMode ? 8 : 6)) {
                qCritical() << "SELF_TEST_FAIL: original dock artwork failed to load"
                            << "ready icons" << iconReadyCount;
                QCoreApplication::exit(1);
                return;
            }
            if (approvedMode)
                qInfo() << "SELF_TEST_PASS: all eight exact approved dock PNGs loaded";
            else
                qInfo() << "SELF_TEST_PASS: all six SVG dock candidates loaded (legacy demo only)";
            if (approvedMode) {
                // A successful icon decoder doesn't prove the dock looks aligned.
                // Test all eight ACTUAL QML image rectangles in the running scene.
                // Each 54px art slot must be centred on its 58x70px button,
                // and its button must be centered vertically inside the dock.
                const QStringList names {
                    QStringLiteral("Browser"), QStringLiteral("Mail"),
                    QStringLiteral("Files"), QStringLiteral("Calendar"),
                    QStringLiteral("Photos"), QStringLiteral("Music"),
                    QStringLiteral("Terminal"), QStringLiteral("Settings")
                };
                qreal previousRight = -1;
                for (const QString &name : names) {
                    auto *button = findDockTile(dock, name);
                    auto *art = button ? findVisualItem(button, QStringLiteral("canopyDockIcon"))
                                       : nullptr;
                    if (!button || !art) {
                        qCritical() << "SELF_TEST_FAIL: dock centering missing control" << name;
                        QCoreApplication::exit(1);
                        return;
                    }
                    const QPointF iconStart = art->mapToItem(dock, QPointF(0, 0));
                    const QPointF tileStart = button->mapToItem(dock, QPointF(0, 0));
                    const qreal iconMidX = iconStart.x() + art->width() / 2;
                    const qreal iconMidY = iconStart.y() + art->height() / 2;
                    const qreal buttonMidX = tileStart.x() + button->width() / 2;
                    const qreal buttonMidY = tileStart.y() + button->height() / 2;
                    if (qAbs(iconMidX - buttonMidX) > 0.75 ||
                        qAbs(iconMidY - buttonMidY) > 0.75 ||
                        qAbs(iconMidY - dock->height() / 2) > 1.0 ||
                        iconStart.y() < 7 || iconStart.y() + art->height()
                             > dock->height() - 7 ||
                        tileStart.x() < previousRight ||
                        art->width() < 50 || art->width() > 56 ||
                        art->height() != art->width()) {
                        qCritical() << "SELF_TEST_FAIL: dock icon optical alignment"
                                    << name << "image" << iconStart << art->size()
                                    << "tile" << tileStart << button->size()
                                    << "dock" << dock->size();
                        QCoreApplication::exit(1);
                        return;
                    }
                    previousRight = tileStart.x() + button->width();
                }
                qInfo() << "SELF_TEST_PASS: eight dock icons horizontally/vertically centred"
                        << "with equal 54px art slots and 7px minimum dock insets";
            }
            if (!wallpaperFits || dockTileCount != (approvedMode ? 8 : 6)) {
                qCritical() << "SELF_TEST_FAIL: wallpaper bounds or dock icon count invalid"
                            << "wallpaper" << wallpaperOrigin << wallpaper->size()
                            << "icon count" << dockTileCount;
                QCoreApplication::exit(1);
                return;
            }
            const int folderCount = countVisualItems(preview, QStringLiteral("canopyFolderTile"));
            const int searchCount = countVisualItems(preview, QStringLiteral("canopyPreviewSearch"));
            if (folderCount != 8 || searchCount != 1) {
                qCritical() << "SELF_TEST_FAIL: sample Files preview content incomplete"
                            << "sample folders" << folderCount << "search inputs" << searchCount;
                QCoreApplication::exit(1);
                return;
            }
            auto *folderScroller = findVisualItem(
                preview, QStringLiteral("canopyFolderScroller"));
            const bool compactMustScroll = window->width() <= 800;
            if (!folderScroller || !folderScroller->clip()
                || (compactMustScroll &&
                    folderScroller->property("contentHeight").toDouble()
                    <= folderScroller->height() + 5)) {
                qCritical() << "SELF_TEST_FAIL: sample folder scrolling unavailable"
                            << "compact" << compactMustScroll
                            << "viewport" << (folderScroller ? folderScroller->height() : 0)
                            << "content" << (folderScroller ?
                                folderScroller->property("contentHeight").toDouble() : 0);
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: compact folder scrolling viewport validated";
            const int folderArtworkReady = countReadyFolderTiles(preview);
            if (folderArtworkReady != 8) {
                qCritical() << "SELF_TEST_FAIL: folder artwork did not load"
                            << "ready sample folders" << folderArtworkReady;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: all eight original sample folder images loaded";
            qInfo() << "SELF_TEST_PASS: eight demo folders and one search control present";
            if (approvedMode && landscapeMode)
                qInfo() << "SELF_TEST_PASS: eight SHA-locked icon PNGs and separate landscape wallpaper present";
            else if (approvedMode)
                qInfo() << "SELF_TEST_PASS: verified user-supplied blue wave and eight selected PNG icons present";
            else
                qInfo() << "SELF_TEST_PASS: original wallpaper and six dock icon candidates present";
            qInfo() << "SELF_TEST_PASS: preview window fits above dock" << previewOrigin
                    << preview->size();
            qInfo() << "SELF_TEST_PASS: desktop chrome geometry" << window->size();
            // Exercise the actual QML Button clicked signal, not only source strings.
            // Toggle twice so the screenshot remains the original visible scene.
            auto *filesTile = findDockTile(dock, QStringLiteral("Files"));
            if (!filesTile || !preview->isVisible() ||
                !filesTile->property("previewActive").toBool() ||
                !QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files dock click setup invalid";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (preview->isVisible() || filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files dock did not hide preview";
                QCoreApplication::exit(1);
                return;
            }
            if (!QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files dock second click failed";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (!preview->isVisible() || !filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files dock did not restore preview";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Files dock hide/restore and activity indicator";
            auto *closeControl = findVisualItem(preview, QStringLiteral("canopyPreviewClose"));
            if (!closeControl ||
                !QMetaObject::invokeMethod(closeControl, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files close control missing or inactive";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (preview->isVisible() || filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files close control did not hide preview";
                QCoreApplication::exit(1);
                return;
            }
            if (!QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files dock could not reopen closed preview";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (!preview->isVisible() || !filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files preview failed to reopen after close";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Files close control and dock reopen";
            // Trigger the QML shortcut signals directly to verify bindings;
            // this does not claim OS-level keyboard dispatch or global hooks.
            auto *closeShortcut = window->findChild<QObject *>(
                QStringLiteral("canopyFilesCloseShortcut"));
            auto *openShortcut = window->findChild<QObject *>(
                QStringLiteral("canopyFilesOpenShortcut"));
            if (!closeShortcut || !openShortcut ||
                !closeShortcut->property("enabled").toBool() ||
                !QMetaObject::invokeMethod(closeShortcut, "activated", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files keyboard close shortcut unavailable";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (preview->isVisible() || !openShortcut->property("enabled").toBool() ||
                !QMetaObject::invokeMethod(openShortcut, "activated", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files keyboard shortcut close/open failed";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (!preview->isVisible() || !closeShortcut->property("enabled").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files keyboard shortcut did not reopen preview";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Files keyboard close and reopen bindings";
            const QImage frame = window->grabWindow();
            if (frame.isNull() || frame.width() < 720 || frame.height() < 480) {
                qCritical() << "SELF_TEST_FAIL: invalid screenshot dimensions";
                QCoreApplication::exit(1);
                return;
            }
            QSet<QRgb> sampledColors;
            for (int y = 0; y < frame.height(); y += qMax(1, frame.height() / 12)) {
                for (int x = 0; x < frame.width(); x += qMax(1, frame.width() / 12)) {
                    sampledColors.insert(frame.pixel(x, y));
                }
            }
            // Prove the *visible wallpaper* varies, without trusting just one
            // chosen sky/foreground pair. Scenic photos may give two similar
            // colors at a narrow display's left edge; both outer strips remain
            // unobscured by the central demo Files window at supported sizes.
            const int edgeX = qMax(2, frame.width() / 100);
            const int edgeXs[] = { edgeX, frame.width() - edgeX - 1 };
            QVector<QRgb> wallpaperSamples;
            for (int x : edgeXs) {
                for (int y = qMax(50, frame.height() / 8);
                     y < frame.height() - 10;
                     y += qMax(1, frame.height() / 10)) {
                    wallpaperSamples.append(frame.pixel(x, y));
                }
            }
            int maxArtworkDifference = 0;
            for (int i = 0; i < wallpaperSamples.size(); ++i) {
                for (int j = 0; j < i; ++j) {
                    const QRgb a = wallpaperSamples.at(i);
                    const QRgb b = wallpaperSamples.at(j);
                    maxArtworkDifference = qMax(maxArtworkDifference,
                        qAbs(qRed(a) - qRed(b)) +
                        qAbs(qGreen(a) - qGreen(b)) +
                        qAbs(qBlue(a) - qBlue(b)));
                }
            }
            if (maxArtworkDifference < 55) {
                qCritical() << "SELF_TEST_FAIL: wallpaper regions unexpectedly uniform"
                            << "maximum color distance" << maxArtworkDifference;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: wallpaper regions visually distinct";
            if (sampledColors.size() < 8) {
                qCritical() << "SELF_TEST_FAIL: screenshot appears blank or uniform";
                QCoreApplication::exit(1);
                return;
            }
            if (!frame.save(screenshotPath, "PNG")) {
                qCritical() << "SELF_TEST_FAIL: could not capture window" << screenshotPath;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: nonuniform window screenshot captured" << frame.size()
                    << "sampled colors" << sampledColors.size();
            QCoreApplication::quit();
        });
    }
    return app.exec();
}
