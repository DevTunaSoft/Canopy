#pragma once

#include <QHash>
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
//   canopy_features/windows/window_state_capabilities.py (known backend ids
//   and the merged PR #688 bounded, generation-checked window references)
//
// The compiled shell already constructs this QObject and feeds it trusted host
// snapshots through applySnapshot(); no timer, service, polling or new host
// topic is added. A host may supply optional `windowRefs` facts in that same
// snapshot; when it does, every focus reference is validated against the
// bounded live generation before any indicator can be derived. The QML face is
// WindowActivationIndicators.qml, an inert QtObject with no visual elements.
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
    // Mirrors window_state_capabilities.MAX_LIVE_WINDOWS / MAX_SERIAL (PR #688).
    static constexpr int kMaxLiveWindows = 64;
    static constexpr int kMaxSerial = 2147483647;

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

    // Decision-only PR #688 gate: a dock activation is refused unless the
    // supplied window reference is LIVE in the last host-supplied registry and
    // owned by the target app. No window operation is performed here.
    Q_INVOKABLE QString resolveActivationWithReference(
        const QString &appId, const QString &originApp, int windowId,
        int serial, const QString &owner) const;

    // Classify one reference against the last host-supplied live generation:
    // LIVE, STALE, UNKNOWN, UNAUTHORIZED, INVALID or UNVALIDATED (no registry).
    Q_INVOKABLE QString referenceStatus(int windowId, int serial,
                                        const QString &owner) const;
    Q_INVOKABLE int liveWindowCount() const;

signals:
    void stateChanged();

private:
    struct Owner {
        int pid = 0;
        QString appId;
    };

    // One host-owned live window instance; the serial is its generation.
    struct WindowRef {
        int windowId = 0;
        int serial = 0;
        QString owner;
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
    bool parseWindowRefs(const QVariantList &values,
                         QHash<int, WindowRef> &live,
                         QHash<int, int> &seenSerial) const;
    static QString classifyReference(const QHash<int, WindowRef> &live,
                                     const QHash<int, int> &seenSerial,
                                     int windowId, int serial,
                                     const QString &owner);
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
    QHash<int, WindowRef> m_liveWindows;
    QHash<int, int> m_seenSerial;  // high-water generation, kept across clears
    bool m_hasRegistry = false;
};
