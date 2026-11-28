// GIO headers must be parsed BEFORE Qt defines its "signals" macro.
// GLib's GDBus structs legitimately contain a member called "signals".
// Without the gio-unix-2.0 dev package the launcher compiles as a disabled
// fallback: every request is refused, so no native app code can run.
#ifdef CANOPY_HAVE_GIO
#include <gio/gdesktopappinfo.h>
#include <gio/gio.h>
#endif

#include "SystemAppLauncher.h"

#include <QHash>
#include <QDebug>

SystemAppLauncher::SystemAppLauncher(bool enabled, QObject *parent)
    : QObject(parent), m_enabled(enabled) {}

QStringList SystemAppLauncher::candidatesFor(const QString &dockName) {
    // Exact dock labels only: no arbitrary desktop IDs, paths, commands,
    // arguments, URLs or free-form user input are accepted at this boundary.
    static const QHash<QString, QStringList> candidates = {
        {QStringLiteral("Browser"), {
            QStringLiteral("firefox.desktop"),
            QStringLiteral("org.mozilla.firefox.desktop"),
            QStringLiteral("chromium.desktop"),
            QStringLiteral("google-chrome.desktop"),
            QStringLiteral("org.gnome.Epiphany.desktop")}},
        {QStringLiteral("Mail"), {
            QStringLiteral("thunderbird.desktop"),
            QStringLiteral("org.mozilla.Thunderbird.desktop"),
            QStringLiteral("org.gnome.Evolution.desktop")}},
        {QStringLiteral("Files"), {
            QStringLiteral("nemo.desktop"),
            QStringLiteral("org.gnome.Nautilus.desktop"),
            QStringLiteral("thunar.desktop")}},
        {QStringLiteral("Calendar"), {
            QStringLiteral("org.gnome.Calendar.desktop"),
            QStringLiteral("org.gnome.Evolution.desktop")}},
        {QStringLiteral("Photos"), {
            QStringLiteral("pix.desktop"),
            QStringLiteral("org.gnome.Loupe.desktop"),
            QStringLiteral("gthumb.desktop")}},
        {QStringLiteral("Music"), {
            QStringLiteral("rhythmbox.desktop"),
            QStringLiteral("org.gnome.Rhythmbox3.desktop"),
            QStringLiteral("org.gnome.Lollypop.desktop")}},
        {QStringLiteral("Terminal"), {
            QStringLiteral("gnome-terminal.desktop"),
            QStringLiteral("org.gnome.Terminal.desktop"),
            QStringLiteral("mate-terminal.desktop"),
            QStringLiteral("xfce4-terminal.desktop"),
            QStringLiteral("org.kde.konsole.desktop"),
            QStringLiteral("konsole.desktop")}},
        {QStringLiteral("Settings"), {
            QStringLiteral("cinnamon-settings.desktop"),
            QStringLiteral("org.gnome.Settings.desktop"),
            QStringLiteral("xfce4-settings-manager.desktop")}},
    };
    return candidates.value(dockName);
}

bool SystemAppLauncher::canLaunch(const QString &dockName) const {
#ifdef CANOPY_HAVE_GIO
    if (!m_enabled)
        return false;
    const QStringList choices = candidatesFor(dockName);
    for (const QString &id : choices) {
        const QByteArray utf8 = id.toUtf8();
        GDesktopAppInfo *info = g_desktop_app_info_new(utf8.constData());
        if (!info)
            continue;
        const bool available = g_app_info_should_show(G_APP_INFO(info));
        g_object_unref(info);
        if (available)
            return true;
    }
    return false;
#else
    Q_UNUSED(dockName);
    return false;
#endif
}

bool SystemAppLauncher::launch(const QString &dockName) const {
#ifdef CANOPY_HAVE_GIO
    if (!m_enabled)
        return false;
    const QStringList choices = candidatesFor(dockName);
    if (choices.isEmpty()) {
        qWarning() << "CANOPY_APP_LAUNCH_REJECTED: unknown dock action";
        return false;
    }
    for (const QString &id : choices) {
        const QByteArray utf8 = id.toUtf8();
        GDesktopAppInfo *info = g_desktop_app_info_new(utf8.constData());
        if (!info)
            continue;
        if (!g_app_info_should_show(G_APP_INFO(info))) {
            g_object_unref(info);
            continue;
        }
        GError *error = nullptr;
        const gboolean started = g_app_info_launch(
            G_APP_INFO(info), nullptr, nullptr, &error);
        if (error)
            g_error_free(error);  // Do not expose paths or command lines in logs.
        g_object_unref(info);
        if (started) {
            qInfo() << "CANOPY_APP_LAUNCH_REQUESTED:" << dockName;
            return true;
        }
        // Don't automatically launch a different app if a present entry failed.
        qWarning() << "CANOPY_APP_LAUNCH_FAILED:" << dockName;
        return false;
    }
    qWarning() << "CANOPY_APP_LAUNCH_UNAVAILABLE:" << dockName;
    return false;
#else
    Q_UNUSED(dockName);
    return false;
#endif
}
