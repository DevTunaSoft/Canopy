#include <QGuiApplication>
#include <QQmlApplicationEngine>

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationDisplayName(QStringLiteral("Canopy Classic Spike"));
    QQmlApplicationEngine engine;
    engine.loadFromModule("Canopy.Classic", "Main");
    if (engine.rootObjects().isEmpty())
        return 1;
    return app.exec();
}
