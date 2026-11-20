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

// A Repeater can give its delegates QObject owners different from their
// visual parents. Traverse the actual QQuickItem scene tree for UI assertions.
static int countVisualItems(QQuickItem *parent, const QString &objectName) {
    if (!parent)
        return 0;
    int count = parent->objectName() == objectName ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        count += countVisualItems(child, objectName);
    return count;
}

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationDisplayName(QStringLiteral("Canopy Classic Spike"));
    QQmlApplicationEngine engine;
    engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")));
    if (engine.rootObjects().isEmpty())
        return 1;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window || !window->isVisible()) {
        qCritical() << "Canopy Classic: QML root did not create a visible window";
        return 1;
    }
    qInfo() << "CANOPY_CLASSIC_WINDOW_READY";
    const QStringList args = QCoreApplication::arguments();
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
        QTimer::singleShot(1000, window, [window, screenshotPath]() {
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
                && qAbs(bar->width() - window->width()) <= 2 && bar->height() >= 40;
            const bool dockFits = dockOrigin.x() >= 0 && dockOrigin.y() >= bar->height()
                && dockOrigin.x() + dock->width() <= window->width() + 1
                && dockOrigin.y() + dock->height() <= window->height() + 1
                && qAbs(dockOrigin.x() + dock->width() / 2 - window->width() / 2) <= 2;
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
            const QPointF wallpaperOrigin = wallpaper->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool wallpaperFits = qAbs(wallpaperOrigin.x()) <= 1
                && qAbs(wallpaperOrigin.y()) <= 1
                && qAbs(wallpaper->width() - window->width()) <= 1
                && qAbs(wallpaper->height() - window->height()) <= 1;
            if (!wallpaperFits || dockTileCount != 7) {
                qCritical() << "SELF_TEST_FAIL: wallpaper bounds or dock icon count invalid"
                            << "wallpaper" << wallpaperOrigin << wallpaper->size()
                            << "icon count" << dockTileCount;
                QCoreApplication::exit(1);
                return;
            }
            const int folderCount = countVisualItems(preview, QStringLiteral("canopyFolderTile"));
            const int searchCount = countVisualItems(preview, QStringLiteral("canopyPreviewSearch"));
            if (folderCount != 6 || searchCount != 1) {
                qCritical() << "SELF_TEST_FAIL: sample Files preview content incomplete"
                            << "sample folders" << folderCount << "search inputs" << searchCount;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: six demo folders and one search control present";
            qInfo() << "SELF_TEST_PASS: original wallpaper and seven dock icons present";
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
