#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QQuickItem>
#include <QtMath>
#include <QDebug>
#include <QTimer>
#include <QCoreApplication>
#include <QImage>
#include <QStringList>
#include <QRegularExpression>
#include <QSet>
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
static bool verifyExactArtwork(const QString &dirPath, QString *error) {
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
    if (!verify(wallpaper) || checkedPaths.size() != 9) {
        if (error->isEmpty())
            *error = QStringLiteral("incomplete approved-art set");
        return false;
    }
    return true;
}

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationDisplayName(QStringLiteral("Canopy Classic Spike"));
    const QStringList args = QCoreApplication::arguments();
    const int approvedIndex = args.indexOf(QStringLiteral("--approved-art-dir"));
    const bool approvedMode = approvedIndex >= 0;
    const bool requireApproved = args.contains(QStringLiteral("--self-test-approved"));
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
        if (!verifyExactArtwork(requested, &error)) {
            qCritical().noquote() << "APPROVED_ART_FAIL:" << error;
            return 3;
        }
        approvedRoot = QDir(requested).canonicalPath();
        qInfo() << "CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and blue wave";
    }
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("canopyApprovedMode"), approvedMode);
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
        QTimer::singleShot(1000, window, [window, screenshotPath, approvedMode]() {
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
                qCritical() << "SELF_TEST_FAIL: Blue Current wallpaper image did not load"
                            << "check Qt SVG plugin and embedded artwork";
                QCoreApplication::exit(1);
                return;
            }
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
            if (approvedMode)
                qInfo() << "SELF_TEST_PASS: verified user-supplied blue wave and eight selected PNG icons present";
            else
                qInfo() << "SELF_TEST_PASS: original wallpaper and six dock icon candidates present";
            qInfo() << "SELF_TEST_PASS: preview window fits above dock" << previewOrigin
                    << preview->size();
            qInfo() << "SELF_TEST_PASS: desktop chrome geometry" << window->size();
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
            // Test the unobscured left edge, so a plain fallback desktop cannot
            // be mistaken for the original artwork despite a nonuniform toolbar.
            const int edgeX = qMax(2, frame.width() / 100);
            const QRgb skyPixel = frame.pixel(edgeX, qMax(50, frame.height() / 7));
            const QRgb foregroundPixel = frame.pixel(edgeX, frame.height() * 85 / 100);
            const int artworkDifference =
                qAbs(qRed(skyPixel) - qRed(foregroundPixel)) +
                qAbs(qGreen(skyPixel) - qGreen(foregroundPixel)) +
                qAbs(qBlue(skyPixel) - qBlue(foregroundPixel));
            if (artworkDifference < 55) {
                qCritical() << "SELF_TEST_FAIL: wallpaper regions unexpectedly uniform"
                            << "color distance" << artworkDifference;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: wallpaper sky and foreground visually distinct";
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
