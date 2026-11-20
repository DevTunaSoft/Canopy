#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QFile>
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
#include <QVariantMap>
#include <QVariantList>

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationDisplayName(QStringLiteral("Canopy Classic Spike"));
    QQmlApplicationEngine engine;
    // All eight icon resources must exist before enabling the artwork path.
    // Default builds remain self-contained and use lightweight Canvas glyphs.
    const QStringList reviewedResourceNames = {
        QStringLiteral("browser"), QStringLiteral("mail"),
        QStringLiteral("files"), QStringLiteral("calendar"),
        QStringLiteral("photos"), QStringLiteral("music"),
        QStringLiteral("terminal"), QStringLiteral("settings")
    };
    bool reviewedIconsAvailable = true;
    for (const QString &name : reviewedResourceNames) {
        if (!QFile::exists(QStringLiteral(":/canopy/classic/icons/") + name + QStringLiteral(".png"))) {
            reviewedIconsAvailable = false;
            break;
        }
    }
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyReviewedIconsAvailable"), reviewedIconsAvailable);
    qInfo() << "CANOPY_CLASSIC_ICON_MODE" << (reviewedIconsAvailable ? "reviewed-resource-preview" : "canvas-fallback");
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
    if (args.contains(QStringLiteral("--self-test-launcher"))
        || args.contains(QStringLiteral("--self-test-search"))) {
        if (!window->setProperty("launcherOpen", true)) {
            qCritical() << "SELF_TEST_FAIL: launcher property unavailable";
            return 2;
        }
    }
    const int screenshotIndex = args.indexOf(QStringLiteral("--self-test-screenshot"));
    if (screenshotIndex >= 0) {
        if (screenshotIndex + 1 >= args.size()) {
            qCritical() << "Missing screenshot output path";
            return 2;
        }
        const QString screenshotPath = args.at(screenshotIndex + 1);
        QTimer::singleShot(1000, window, [window, screenshotPath, reviewedIconsAvailable]() {
            auto *bar = window->findChild<QQuickItem *>(QStringLiteral("canopyTopBar"));
            auto *dock = window->findChild<QQuickItem *>(QStringLiteral("canopyDock"));
            auto *launcher = window->findChild<QQuickItem *>(QStringLiteral("canopyLauncher"));
            auto *appOverlay = window->findChild<QQuickItem *>(QStringLiteral("canopyApplicationLauncher"));
            auto *preview = window->findChild<QQuickItem *>(QStringLiteral("canopyPreviewWindow"));
            if (!bar || !dock || !launcher || !preview || !appOverlay) {
                qCritical() << "SELF_TEST_FAIL: missing required desktop chrome";
                QCoreApplication::exit(1);
                return;
            }
            // Runtime contract: both presentations must show exactly the
            // eight user-approved application names, in one shared order.
            // This deliberately checks instantiated Qt objects, not source text.
            const QStringList expectedApps = {
                QStringLiteral("Browser"), QStringLiteral("Mail"),
                QStringLiteral("Files"), QStringLiteral("Calendar"),
                QStringLiteral("Photos"), QStringLiteral("Music"),
                QStringLiteral("Terminal"), QStringLiteral("Settings")
            };
            const QVariantList catalog = window->property("classicApps").toList();
            auto *dockRepeater = window->findChild<QObject *>(
                QStringLiteral("canopyDockRepeater"));
            bool catalogMatches = catalog.size() == expectedApps.size()
                && dockRepeater && dockRepeater->property("count").toInt() == expectedApps.size();
            for (int i = 0; catalogMatches && i < expectedApps.size(); ++i) {
                const QVariantMap appEntry = catalog.at(i).toMap();
                catalogMatches = appEntry.value(QStringLiteral("name")).toString() == expectedApps.at(i)
                    && appEntry.value(QStringLiteral("icon")).toString() == expectedApps.at(i);
            }
            const bool launcherMatches = appOverlay->property("resultCount").toInt() == expectedApps.size();
            if (!catalogMatches || !launcherMatches) {
                qCritical() << "SELF_TEST_FAIL: Classic approved application catalog mismatch"
                            << "catalog" << catalog.size()
                            << "dock" << (dockRepeater ? dockRepeater->property("count") : QVariant())
                            << "launcher" << appOverlay->property("resultCount");
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Classic eight-app dock and launcher catalog";
            if (QCoreApplication::arguments().contains(QStringLiteral("--self-test-icons"))) {
                if (!reviewedIconsAvailable) {
                    qCritical() << "SELF_TEST_FAIL: reviewed icon resources not enabled";
                    QCoreApplication::exit(1);
                    return;
                }
                // Decode every compiled PNG rather than trusting resource path
                // existence. This catches empty, corrupt and unsupported art.
                for (const QString &appName : expectedApps) {
                    const QString resource = QStringLiteral(":/canopy/classic/icons/")
                        + appName.toLower() + QStringLiteral(".png");
                    QImageReader reader(resource);
                    const QImage decoded = reader.read();
                    if (decoded.isNull() || decoded.width() < 256 || decoded.height() < 256
                        || !decoded.hasAlphaChannel()) {
                        qCritical() << "SELF_TEST_FAIL: reviewed icon decode" << resource << reader.errorString();
                        QCoreApplication::exit(1);
                        return;
                    }
                }
                // Also inspect the actual instantiated QML Image nodes. The
                // dock is always visible; the launcher may virtualize cells.
                QSet<QString> qmlIconSources;
                const auto iconImages = window->findChildren<QQuickItem *>(
                    QStringLiteral("canopyReviewedIconImage"));
                for (auto *iconImage : iconImages) {
                    if (iconImage->property("status").toInt() == 1) {
                        qmlIconSources.insert(iconImage->property("source").toUrl().toString());
                    }
                }
                for (const QString &appName : expectedApps) {
                    const QString url = QStringLiteral("qrc:/canopy/classic/icons/")
                        + appName.toLower() + QStringLiteral(".png");
                    if (!qmlIconSources.contains(url)) {
                        qCritical() << "SELF_TEST_FAIL: reviewed icon QML image not ready"
                                    << url << qmlIconSources;
                        QCoreApplication::exit(1);
                        return;
                    }
                }
                qInfo() << "SELF_TEST_PASS: eight reviewed icon PNGs decoded and QML images ready";
            }
            if (QCoreApplication::arguments().contains(QStringLiteral("--self-test-search"))) {
                auto *searchField = window->findChild<QObject *>(
                    QStringLiteral("canopyLauncherSearch"));
                if (!searchField || !appOverlay->isVisible()) {
                    qCritical() << "SELF_TEST_FAIL: search control unavailable";
                    QCoreApplication::exit(1);
                    return;
                }
                // Exercise the live QML binding, including case-folding,
                // no-match and restoration; no external programs are run.
                searchField->setProperty("text", QStringLiteral("mUsIc"));
                QCoreApplication::processEvents();
                const bool matchOne = appOverlay->property("resultCount").toInt() == 1;
                searchField->setProperty("text", QStringLiteral("zz-canopy-no-match"));
                QCoreApplication::processEvents();
                const bool matchNone = appOverlay->property("resultCount").toInt() == 0;
                searchField->setProperty("text", QString());
                QCoreApplication::processEvents();
                const bool restored = appOverlay->property("resultCount").toInt() == 8;
                if (!matchOne || !matchNone || !restored) {
                    qCritical() << "SELF_TEST_FAIL: Classic live application search"
                                << matchOne << matchNone << restored;
                    QCoreApplication::exit(1);
                    return;
                }
                qInfo() << "SELF_TEST_PASS: Classic live application search";
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
                && previewOrigin.y() + preview->height() <= dockOrigin.y() - 2
                && preview->width() >= 480 && preview->height() >= 250;
            if (!previewFits) {
                qCritical() << "SELF_TEST_FAIL: preview overlaps desktop chrome or is too small"
                            << "window" << window->size() << "preview" << previewOrigin
                            << preview->size() << "dock" << dockOrigin << dock->size();
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: preview window fits above dock" << previewOrigin
                    << preview->size();
            if (QCoreApplication::arguments().contains(QStringLiteral("--self-test-launcher"))) {
                auto *panel = window->findChild<QQuickItem *>(QStringLiteral("canopyLauncherPanel"));
                auto *search = window->findChild<QQuickItem *>(QStringLiteral("canopyLauncherSearch"));
                auto *grid = window->findChild<QQuickItem *>(QStringLiteral("canopyLauncherGrid"));
                const QPointF panelOrigin = panel
                    ? panel->mapToItem(window->contentItem(), QPointF(0, 0))
                    : QPointF(-1, -1);
                const bool panelFits = panel
                    && panelOrigin.y() >= bar->height() + 2
                    && panelOrigin.y() + panel->height() <= dockOrigin.y() - 2;
                const bool allRowsFit = grid
                    && grid->property("contentHeight").toDouble() <= grid->height() + 2;
                if (!appOverlay->isVisible() || !panel || !search || !grid
                    || panel->width() <= 400 || panel->height() <= 250
                    || grid->width() < 300 || grid->height() < 100
                    || !panelFits || !allRowsFit) {
                    qCritical() << "SELF_TEST_FAIL: application launcher clipping, overlap, or geometry" << panelOrigin;
                    QCoreApplication::exit(1);
                    return;
                }
                qInfo() << "SELF_TEST_PASS: application launcher geometry";
            }
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
