// Fixture-only driver: compiles the UNMODIFIED SystemAppLauncher.cpp from the
// pinned integration tip against the fake GIO shim (or with GIO compiled out).
// It prints one CASE_PASS/CASE_FAIL line per assertion and exits non-zero on
// any failure. Visual assets, QML and production sources are never written.
#include "SystemAppLauncher.h"
#include <fake_gio_test_api.h>

#include <QCoreApplication>
#include <QDebug>
#include <QFile>
#include <QStringList>
#include <QTextStream>

#include <cstdio>

namespace {

QStringList capturedMessages;

void captureMessages(QtMsgType type, const QMessageLogContext &context,
                     const QString &message) {
    Q_UNUSED(type);
    Q_UNUSED(context);
    capturedMessages.append(message);
}

QStringList readLog(const QString &path) {
    QStringList lines;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
        return lines;
    QTextStream stream(&file);
    while (!stream.atEnd()) {
        const QString line = stream.readLine();
        if (!line.isEmpty())
            lines.append(line);
    }
    return lines;
}

bool hasMessage(const QString &fragment) {
    for (const QString &message : capturedMessages) {
        if (message.contains(fragment))
            return true;
    }
    return false;
}

int countPrefix(const QStringList &lines, const QString &prefix) {
    int count = 0;
    for (const QString &line : lines) {
        if (line.startsWith(prefix))
            ++count;
    }
    return count;
}

void report(const QString &name, bool passed, const QString &detail) {
    if (passed)
        printf("CASE_PASS: %s | %s\n", qPrintable(name), qPrintable(detail));
    else {
        printf("CASE_FAIL: %s | %s\n", qPrintable(name), qPrintable(detail));
        printf("DEBUG_MESSAGES: %s\n",
               qPrintable(capturedMessages.join(QStringLiteral(" ~~ "))));
    }
}

#ifndef NO_GIO_BUILD
struct Target {
    const char *label;
    const char *firstId;
};

bool positiveMapping(const Target &target, const QString &logPath) {
    fake_gio_reset_log();
    fake_gio_configure(target.firstId, "", qPrintable(logPath));
    capturedMessages.clear();

    SystemAppLauncher launcher(true);
    const bool canLaunch = launcher.canLaunch(QString::fromLatin1(target.label));
    const bool launched = launcher.launch(QString::fromLatin1(target.label));
    const QString id = QString::fromLatin1(target.firstId);
    // canLaunch() -> new+should_show; launch() -> new+should_show+launch.
    const QStringList expected = {
        QStringLiteral("new ") + id,
        QStringLiteral("should_show ") + id,
        QStringLiteral("new ") + id,
        QStringLiteral("should_show ") + id,
        QStringLiteral("launch ") + id,
    };
    const QStringList actual = readLog(logPath);
    const bool passed = canLaunch && launched && actual == expected
        && hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_REQUESTED: \"")
                      + QString::fromLatin1(target.label) + QStringLiteral("\""))
        && !hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_REJECTED"))
        && !hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_FAILED"))
        && !hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_UNAVAILABLE"));
    const QString detail = QStringLiteral("can=%1 launch=%2 calls=%3")
        .arg(canLaunch).arg(launched).arg(actual.join(QStringLiteral(" > ")));
    report(QStringLiteral("mapping:%1").arg(QString::fromLatin1(target.label)),
           passed, detail);
    return passed;
}

bool fallbackOrder(const QString &logPath) {
    const char *first = "firefox.desktop";
    const char *second = "org.mozilla.firefox.desktop";
    fake_gio_reset_log();
    fake_gio_configure(second, "", qPrintable(logPath));
    capturedMessages.clear();

    SystemAppLauncher launcher(true);
    const bool canLaunch = launcher.canLaunch(QStringLiteral("Browser"));
    const bool launched = launcher.launch(QStringLiteral("Browser"));
    const QStringList expected = {
        QStringLiteral("new firefox.desktop"),
        QStringLiteral("new org.mozilla.firefox.desktop"),
        QStringLiteral("should_show org.mozilla.firefox.desktop"),
        QStringLiteral("new firefox.desktop"),
        QStringLiteral("new org.mozilla.firefox.desktop"),
        QStringLiteral("should_show org.mozilla.firefox.desktop"),
        QStringLiteral("launch org.mozilla.firefox.desktop"),
    };
    const QStringList actual = readLog(logPath);
    const bool passed = canLaunch && launched && actual == expected;
    report(QStringLiteral("mapping:Browser-fallback-order"), passed,
           QStringLiteral("can=%1 launch=%2 calls=%3")
               .arg(canLaunch).arg(launched)
               .arg(actual.join(QStringLiteral(" > "))));
    return passed;
}

bool disabledRefusal(const QString &logPath) {
    fake_gio_reset_log();
    fake_gio_configure("firefox.desktop", "", qPrintable(logPath));
    capturedMessages.clear();

    SystemAppLauncher launcher(false);
    const bool canLaunch = launcher.canLaunch(QStringLiteral("Browser"));
    const bool launched = launcher.launch(QStringLiteral("Browser"));
    const QStringList actual = readLog(logPath);
    const bool passed = !canLaunch && !launched && actual.isEmpty();
    report(QStringLiteral("refusal:opt-in-disabled"), passed,
           QStringLiteral("gio_calls=%1").arg(actual.size()));
    return passed;
}

bool unknownActionRefusal(const QString &logPath) {
    fake_gio_reset_log();
    fake_gio_configure("firefox.desktop,gnome-terminal.desktop,nemo.desktop",
                       "", qPrintable(logPath));
    capturedMessages.clear();

    SystemAppLauncher launcher(true);
    const bool canLaunch = launcher.canLaunch(QStringLiteral("firefox.desktop"));
    const bool launched = launcher.launch(QStringLiteral("Browser;echo hacked"));
    const bool emptyLaunch = launcher.launch(QStringLiteral(""));
    const QStringList actual = readLog(logPath);
    const bool passed = !canLaunch && !launched && !emptyLaunch
        && actual.isEmpty()
        && hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_REJECTED: unknown dock action"));
    report(QStringLiteral("refusal:unknown-action"), passed,
           QStringLiteral("gio_calls=%1 message=%2")
               .arg(actual.size())
               .arg(hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_REJECTED"))));
    return passed;
}

bool unavailableRefusal(const QString &logPath) {
    fake_gio_reset_log();
    fake_gio_configure("", "", qPrintable(logPath));
    capturedMessages.clear();

    SystemAppLauncher launcher(true);
    const bool canLaunch = launcher.canLaunch(QStringLiteral("Terminal"));
    const bool launched = launcher.launch(QStringLiteral("Terminal"));
    const QStringList actual = readLog(logPath);
    const bool passed = !canLaunch && !launched
        && countPrefix(actual, QStringLiteral("new ")) == 8
        && countPrefix(actual, QStringLiteral("should_show ")) == 0
        && countPrefix(actual, QStringLiteral("launch ")) == 0
        && hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_UNAVAILABLE: \"Terminal\""));
    report(QStringLiteral("refusal:unavailable"), passed,
           QStringLiteral("can=%1 launch=%2 new_calls=%3")
               .arg(canLaunch).arg(launched)
               .arg(countPrefix(actual, QStringLiteral("new "))));
    return passed;
}

bool launchFailureNoFallback(const QString &logPath) {
    fake_gio_reset_log();
    fake_gio_configure("gnome-terminal.desktop", "gnome-terminal.desktop",
                       qPrintable(logPath));
    capturedMessages.clear();

    SystemAppLauncher launcher(true);
    const bool canLaunch = launcher.canLaunch(QStringLiteral("Terminal"));
    const bool launched = launcher.launch(QStringLiteral("Terminal"));
    const QStringList actual = readLog(logPath);
    const bool passed = canLaunch && !launched
        && countPrefix(actual, QStringLiteral("launch ")) == 1
        && !actual.contains(QStringLiteral("launch mate-terminal.desktop"))
        && !actual.contains(QStringLiteral("launch xfce4-terminal.desktop"))
        && hasMessage(QStringLiteral("CANOPY_APP_LAUNCH_FAILED: \"Terminal\""));
    report(QStringLiteral("refusal:launch-failure-no-fallback"), passed,
           QStringLiteral("can=%1 launch=%2 launch_calls=%3")
               .arg(canLaunch).arg(launched)
               .arg(countPrefix(actual, QStringLiteral("launch "))));
    return passed;
}
#endif

bool gioLessFallback() {
    capturedMessages.clear();
    SystemAppLauncher launcher(true);
    bool passed = true;
    const char *labels[] = {"Browser", "Terminal", "Calendar",
                            "Photos", "Mail", "Files", "Unknown"};
    for (const char *label : labels) {
        const bool canLaunch = launcher.canLaunch(QString::fromLatin1(label));
        const bool launched = launcher.launch(QString::fromLatin1(label));
        if (canLaunch || launched)
            passed = false;
    }
    report(QStringLiteral("refusal:no-gio-fallback-build"), passed,
           QStringLiteral("7 labels x (canLaunch,launch) all false"));
    return passed;
}

}  // namespace

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    qInstallMessageHandler(captureMessages);
    if (argc < 2) {
        fprintf(stderr, "usage: %s <fake-gio-log-path>\n", argv[0]);
        return 2;
    }
    const QString logPath = QString::fromLocal8Bit(argv[1]);
    bool allPassed = true;
    int cases = 0;

#ifdef NO_GIO_BUILD
    allPassed = gioLessFallback();
    cases = 1;
#else
    const Target targets[] = {
        {"Browser",  "firefox.desktop"},
        {"Terminal", "gnome-terminal.desktop"},
        {"Calendar", "org.gnome.Calendar.desktop"},
        {"Photos",   "pix.desktop"},
        {"Mail",     "thunderbird.desktop"},
        {"Files",    "nemo.desktop"},
    };
    for (const Target &target : targets) {
        allPassed = positiveMapping(target, logPath) && allPassed;
        ++cases;
    }
    allPassed = fallbackOrder(logPath) && allPassed;
    ++cases;
    allPassed = disabledRefusal(logPath) && allPassed;
    ++cases;
    allPassed = unknownActionRefusal(logPath) && allPassed;
    ++cases;
    allPassed = unavailableRefusal(logPath) && allPassed;
    ++cases;
    allPassed = launchFailureNoFallback(logPath) && allPassed;
    ++cases;
#endif

    printf("SUMMARY: cases=%d result=%s\n", cases,
           allPassed ? "ALL_PASS" : "FAIL");
    return allPassed ? 0 : 1;
}
