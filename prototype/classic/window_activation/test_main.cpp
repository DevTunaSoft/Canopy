#include "WindowActivationState.h"

#include <QCoreApplication>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QQmlComponent>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQmlExpression>
#include <QStringList>
#include <QUrl>
#include <QVariant>

#include <stdio.h>

namespace {

QVariant toVariant(const QJsonValue &value)
{
    switch (value.type()) {
    case QJsonValue::Null:
        return QVariant();
    case QJsonValue::Bool:
        return value.toBool();
    case QJsonValue::Double:
        return value.toDouble();
    case QJsonValue::String:
        return value.toString();
    case QJsonValue::Array: {
        QVariantList list;
        const QJsonArray array = value.toArray();
        for (const QJsonValue &item : array) {
            list.append(toVariant(item));
        }
        return list;
    }
    case QJsonValue::Object: {
        QVariantMap map;
        const QJsonObject object = value.toObject();
        for (auto it = object.constBegin(); it != object.constEnd(); ++it) {
            map.insert(it.key(), toVariant(it.value()));
        }
        return map;
    }
    }
    return QVariant();
}

QVariantMap toMap(const QJsonValue &value)
{
    return toVariant(value).toMap();
}

QString fail(const QString &name, const QString &detail)
{
    printf("VECTOR_FAIL %s %s\n", qPrintable(name), qPrintable(detail));
    return detail;
}

bool checkCase(const QJsonObject &testCase, int &failures)
{
    const QString name = testCase.value(QStringLiteral("name")).toString();
    const QVariantMap snapshot = toMap(testCase.value(QStringLiteral("snapshot")));
    WindowActivationState state;

    if (testCase.contains(QStringLiteral("preapply"))) {
        const QVariantMap pre = toMap(testCase.value(QStringLiteral("preapply")));
        if (!state.applySnapshot(pre)) {
            fail(name, QStringLiteral("preapply rejected"));
            ++failures;
            return false;
        }
    }

    const bool applied = state.applySnapshot(snapshot);
    const QJsonObject expected = testCase.value(QStringLiteral("expected")).toObject();
    const QString expectedStatus = expected.value(QStringLiteral("status")).toString();
    const int expectedSequence = static_cast<int>(
        expected.value(QStringLiteral("sequence")).toDouble());
    const bool expectedApplied = expected.value(QStringLiteral("applied")).toBool();
    const bool expectedTrusted = expected.value(QStringLiteral("trusted")).toBool();

    int local = 0;
    if (applied != expectedApplied) {
        local += fail(name, QStringLiteral("applied mismatch")).size() > 0;
    }
    if (state.backendTrusted() != expectedTrusted) {
        local += fail(name, QStringLiteral("trusted mismatch")).size() > 0;
    }
    if (state.status() != expectedStatus) {
        local += fail(name, QStringLiteral("status mismatch: ") + state.status()).size() > 0;
    }
    if (state.sequence() != expectedSequence) {
        local += fail(name, QStringLiteral("sequence mismatch: ")
                      + QString::number(state.sequence())).size() > 0;
    }

    QStringList expectedRunning;
    const QJsonArray running = expected.value(QStringLiteral("running")).toArray();
    for (const QJsonValue &item : running) {
        expectedRunning.append(item.toString());
    }
    if (state.runningApps() != expectedRunning) {
        local += fail(name, QStringLiteral("running mismatch: [")
                      + state.runningApps().join(',') + ']').size() > 0;
    }
    QStringList expectedActive;
    const QJsonArray active = expected.value(QStringLiteral("active")).toArray();
    for (const QJsonValue &item : active) {
        expectedActive.append(item.toString());
    }
    if (state.activeApps() != expectedActive) {
        local += fail(name, QStringLiteral("active mismatch: [")
                      + state.activeApps().join(',') + ']').size() > 0;
    }

    const QJsonObject resolutions =
        expected.value(QStringLiteral("resolutions")).toObject();
    for (auto it = resolutions.constBegin(); it != resolutions.constEnd(); ++it) {
        const QStringList parts = it.key().split('|');
        if (parts.size() != 2) {
            local += fail(name, QStringLiteral("bad vector key")).size() > 0;
            continue;
        }
        const QString actual = state.resolveActivation(parts.at(0), parts.at(1));
        if (actual != it.value().toString()) {
            local += fail(name, QStringLiteral("resolution ") + it.key()
                          + QStringLiteral(" = ") + actual).size() > 0;
        }
    }

    if (local == 0) {
        printf("VECTOR_PASS %s\n", qPrintable(name));
    } else {
        failures += local;
    }
    return local == 0;
}

QString invokeCheck(QQmlEngine *engine, QObject *object, const QString &method)
{
    QQmlExpression expression(engine->rootContext(), object, method + QStringLiteral("()"));
    const QVariant value = expression.evaluate();
    if (expression.hasError()) {
        return QStringLiteral("qml error: ") + expression.error().toString();
    }
    if (value.typeId() != QMetaType::QString) {
        return QStringLiteral("non-string result from ") + method;
    }
    return value.toString();
}

int runQmlChecks(const QString &vectorsPath, const QString &adapterPath,
                 const QString &selfTestPath)
{
    QFile file(vectorsPath);
    if (!file.open(QIODevice::ReadOnly)) {
        printf("QML_FAIL vectors unreadable\n");
        return 1;
    }
    const QJsonObject root = QJsonDocument::fromJson(file.readAll()).object();
    QVariantMap validSnapshot;
    for (const QJsonValue &value : root.value(QStringLiteral("cases")).toArray()) {
        const QJsonObject testCase = value.toObject();
        if (testCase.value(QStringLiteral("name")).toString()
                == QStringLiteral("fresh_valid_indicators_and_intents")) {
            validSnapshot = toMap(testCase.value(QStringLiteral("snapshot")));
        }
    }
    if (validSnapshot.isEmpty()) {
        printf("QML_FAIL valid vector missing\n");
        return 1;
    }

    WindowActivationState state;
    QQmlEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("activation"), &state);

    QQmlComponent adapterComponent(&engine, QUrl::fromLocalFile(adapterPath));
    if (adapterComponent.isError()) {
        printf("QML_FAIL adapter: %s\n", qPrintable(adapterComponent.errorString()));
        return 1;
    }
    QObject *adapter = adapterComponent.create();
    if (!adapter) {
        printf("QML_FAIL adapter create\n");
        return 1;
    }
    adapter->setProperty("state", QVariant::fromValue(static_cast<QObject *>(&state)));

    engine.rootContext()->setContextProperty(QStringLiteral("adapter"), adapter);
    QQmlComponent testComponent(&engine, QUrl::fromLocalFile(selfTestPath));
    if (testComponent.isError()) {
        printf("QML_FAIL selftest: %s\n", qPrintable(testComponent.errorString()));
        return 1;
    }
    QObject *selfTest = testComponent.create();
    if (!selfTest) {
        printf("QML_FAIL selftest create\n");
        return 1;
    }

    int failures = 0;
    const QString untrusted = invokeCheck(&engine, selfTest, QStringLiteral("checkUntrusted"));
    if (!untrusted.isEmpty()) {
        printf("QML_FAIL untrusted %s\n", qPrintable(untrusted));
        ++failures;
    } else {
        printf("QML_PASS untrusted\n");
    }

    if (!state.applySnapshot(validSnapshot)) {
        printf("QML_FAIL valid snapshot rejected\n");
        return 1;
    }
    const QString ready = invokeCheck(&engine, selfTest, QStringLiteral("checkReady"));
    if (!ready.isEmpty()) {
        printf("QML_FAIL ready %s\n", qPrintable(ready));
        ++failures;
    } else {
        printf("QML_PASS ready\n");
    }

    QVariantMap invalid = validSnapshot;
    QVariantList owners = invalid.value(QStringLiteral("owners")).toList();
    owners.append(owners.constFirst());  // duplicate pid: fail closed
    invalid.insert(QStringLiteral("owners"), owners);
    invalid.insert(QStringLiteral("sequence"), 2.0);
    if (state.applySnapshot(invalid)) {
        printf("QML_FAIL invalid snapshot accepted\n");
        return 1;
    }
    const QString cleared = invokeCheck(&engine, selfTest, QStringLiteral("checkCleared"));
    if (!cleared.isEmpty()) {
        printf("QML_FAIL cleared %s\n", qPrintable(cleared));
        ++failures;
    } else {
        printf("QML_PASS cleared\n");
    }
    return failures == 0 ? 0 : 1;
}

}  // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    const QStringList args = app.arguments();
    if (args.size() < 4) {
        printf("usage: window-activation-self-test <vectors.json> <adapter.qml> <selftest.qml>\n");
        return 2;
    }

    QFile file(args.at(1));
    if (!file.open(QIODevice::ReadOnly)) {
        printf("VECTORS_FAIL unreadable %s\n", qPrintable(args.at(1)));
        return 2;
    }
    const QJsonObject root = QJsonDocument::fromJson(file.readAll()).object();
    const QJsonArray cases = root.value(QStringLiteral("cases")).toArray();
    int failures = 0;
    for (const QJsonValue &value : cases) {
        checkCase(value.toObject(), failures);
    }
    const int qmlFailures = runQmlChecks(args.at(1), args.at(2), args.at(3));
    failures += qmlFailures;

    if (failures == 0) {
        printf("WINDOW_ACTIVATION_SELF_TEST_PASS cases=%d qml=ok\n", cases.size());
        return 0;
    }
    printf("WINDOW_ACTIVATION_SELF_TEST_FAIL failures=%d\n", failures);
    return 1;
}
