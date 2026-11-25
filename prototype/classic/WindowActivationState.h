#pragma once

#include <QList>
#include <QMetaType>
#include <QObject>
#include <QSet>
#include <QString>
#include <QStringList>
#include <QVariant>
#include <QVariantList>
#include <QVariantMap>

// Host-facing, fail-closed running-indicator and window-activation *intent*
// state for the Classic dock. This class never observes the desktop, never
// launches or focuses a process, never polls and never draws anything: a
// trusted host applies one immutable snapshot at a time and this class only
// decides what a dock is allowed to show and which intent a click resolves to.
//
// Contract sources (pure, already-tested modules):
//   canopy_features/dock/dock_running_indicators.py  (bounded owner fold)
//   canopy_features/dock/click_intents.py            (FOCUS/LAUNCH/REJECT/IGNORE)
//   canopy_features/windows/focus_intents.py         (deny-by-default authorization)
//   canopy_features/windows/window_state_capabilities.py (known backend ids)
//
// Wiring dependency: prototype/classic/CMakeLists.txt and main.cpp are owned
// by other workstreams; this file is deliberately NOT registered there. The
// standalone compiled self-test in window_activation/ builds it directly.
class WindowActivationState final : public QObject {
    Q_OBJECT
public:
    // Snapshot keys are allowlisted; every other key is ignored.
    static constexpr int kSchema = 1;
    static constexpr int kMaxApps = 64;
    static constexpr int kMaxPidsPerApp = 8;
    static constexpr int kMaxPid = 2147483647;
    static constexpr int kMaxIdLength = 128;
    static constexpr int kMaxGrants = 256;
    static constexpr int kMaxInstalled = 64;

    explicit WindowActivationState(QObject *parent = nullptr);

    Q_PROPERTY(int sequence READ sequence NOTIFY stateChanged)
    Q_PROPERTY(bool backendTrusted READ backendTrusted NOTIFY stateChanged)
    Q_PROPERTY(QString status READ status NOTIFY stateChanged)
    Q_PROPERTY(QStringList runningApps READ runningApps NOTIFY stateChanged)
    Q_PROPERTY(QStringList activeApps READ activeApps NOTIFY stateChanged)

    int sequence() const { return m_sequence; }
    bool backendTrusted() const { return m_trusted; }
    QString status() const;
    QStringList runningApps() const;
    QStringList activeApps() const;

    // Apply one host snapshot. Returns true only for a fresh, fully valid
    // snapshot. Stale sequences are ignored; invalid snapshots CLEAR all
    // indicators and remove trust before any UI can derive an indicator.
    Q_INVOKABLE bool applySnapshot(const QVariantMap &snapshot);

    Q_INVOKABLE bool isRunning(const QString &appId) const;
    Q_INVOKABLE int runningPidCount(const QString &appId) const;
    Q_INVOKABLE bool isActive(const QString &appId) const;

    // Resolve one dock activation to FOCUS, LAUNCH, REJECT or IGNORE.
    // Returns an intent only; this class never actuates it.
    Q_INVOKABLE QString resolveActivation(const QString &appId,
                                          const QString &originApp) const;

signals:
    void stateChanged();

private:
    struct Owner {
        int pid = 0;
        QString appId;
    };

    static bool isApprovedDockName(const QString &name);
    static bool isApprovedOrigin(const QString &name);
    static bool isKnownBackend(const QString &name);
    static bool asInt(const QVariant &value, int &out);
    static bool asString(const QVariant &value, QString &out);
    static bool asBool(const QVariant &value, bool &out);
    bool parseOwners(const QVariantList &values, QList<Owner> &out) const;
    bool parseInstalled(const QVariantList &values, QSet<QString> &out) const;
    bool parseGrants(const QVariantList &values, QSet<QString> &out) const;
    bool authorized(const QString &origin, const QString &target) const;
    void clear();

    int m_sequence = -1;               // mirrors empty_state() in the Python model
    bool m_trusted = false;
    bool m_launcherEnabled = false;
    QList<Owner> m_owners;
    QSet<QString> m_installed;
    QSet<QString> m_grants;
    QString m_focusApp;
    bool m_focusGranted = false;
};
