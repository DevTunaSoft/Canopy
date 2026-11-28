#include "NativeTaskBoard.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QDebug>
#include <QUrl>

int main(int argc, char **argv)
{
    QGuiApplication app(argc, argv);
    const QStringList args = app.arguments();
    bool autoSequence = args.contains(QStringLiteral("--auto"));
    QString qmlPath;
    for (int i = 1; i < args.size(); ++i) {
        if (!args.at(i).startsWith(QLatin1Char('-')))
            qmlPath = args.at(i);
    }
    if (qmlPath.isEmpty())
        qmlPath = QStringLiteral("NativeTaskHarness.qml");

    NativeTaskBoard board;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("canopyNativeTasks"), &board);
    engine.rootContext()->setContextProperty(QStringLiteral("canopyApprovedMode"), false);
    engine.rootContext()->setContextProperty(QStringLiteral("autoSequence"), autoSequence);
    engine.load(QUrl::fromLocalFile(qmlPath));
    if (engine.rootObjects().isEmpty()) {
        qCritical() << "CANOPY_NATIVE_TASK_HARNESS_FAIL qml load";
        return 2;
    }
    qInfo().noquote() << "CANOPY_NATIVE_TASK_HARNESS_READY" << qmlPath
                      << (autoSequence ? "auto=1" : "auto=0");
    return app.exec();
}
