#pragma once

#include <QHash>
#include <QObject>
#include <QString>
#include <QStringList>

class QAbstractItemModel;
class QModelIndex;

// Read-only, event-driven projection of ONE upstream TaskManager model.
//
// This object never constructs, owns or searches a task model. A trusted host
// injects the single authoritative QAbstractItemModel (PR #730 pattern), and
// every live fact is rebuilt synchronously from that model's own signals.
// There is no timer, poll, thread, socket, process launch or desktop walk.
// Malformed or oversized rows fail closed: the previous immutable snapshot is
// discarded and no running/active claim is published.
class NativeTaskBoard final : public QObject {
    Q_OBJECT
public:
    static constexpr int kMaxRows = 256;
    static constexpr int kMaxIdChars = 128;
    static constexpr int kMaxPid = 2147483647;
    static constexpr int kMaxSequence = 2147483647;

    explicit NativeTaskBoard(QObject *parent = nullptr);
    ~NativeTaskBoard() override;

    Q_PROPERTY(bool attached READ attached NOTIFY stateChanged)
    Q_PROPERTY(int sequence READ sequence NOTIFY stateChanged)
    Q_PROPERTY(int rowCount READ rowCount NOTIFY stateChanged)
    Q_PROPERTY(QStringList runningApps READ runningApps NOTIFY stateChanged)
    Q_PROPERTY(QStringList activeApps READ activeApps NOTIFY stateChanged)

    bool attached() const { return m_model != nullptr; }
    int sequence() const { return m_sequence; }
    int rowCount() const { return m_rowCount; }
    QStringList runningApps() const { return m_runningApps; }
    QStringList activeApps() const { return m_activeApps; }

    // The first injection wins. Re-injection of another model is refused so a
    // second authoritative task source can never be introduced.
    Q_INVOKABLE bool attachModel(QObject *modelObject);
    Q_INVOKABLE void detachModel();

    Q_INVOKABLE bool isRunning(const QString &appId) const;
    Q_INVOKABLE bool isActive(const QString &appId) const;
    Q_INVOKABLE int rowFor(const QString &appId) const;
    Q_INVOKABLE int launcherRowFor(const QString &appId) const;
    Q_INVOKABLE QString launcherUrlFor(const QString &appId) const;

    // Deterministic, sorted log shape (no host facts invented).
    Q_INVOKABLE QString snapshotJson() const;
    Q_INVOKABLE void logEvent(const QString &event);

    // Explicit synchronous rebuild; used by attachModel and by direct model
    // signal connections. It is not a poll and is never called on a timer.
    void rebuild();

    static QString canonicalId(const QString &raw);

signals:
    void stateChanged();

private:
    struct Roles {
        int appId = -1;
        int appPid = -1;
        int isWindow = -1;
        int isActive = -1;
        int launcherUrl = -1;
        int display = -1;
    };

    struct Row {
        QString appId;
        int pid = 0;
        bool isWindow = false;
        bool isActive = false;
        QString launcherUrl;
        QString display;
    };

    static bool resolveRoles(QAbstractItemModel *model, Roles *out);
    static QVariant roleData(QAbstractItemModel *model, int row,
                             int role, const QModelIndex &parent);
    void clearFailClosed();
    void connectModel(QAbstractItemModel *model);
    void disconnectModel();

    QAbstractItemModel *m_model = nullptr;
    Roles m_roles;
    QHash<QString, int> m_windowRows;
    QHash<QString, int> m_launcherRows;
    QHash<QString, QString> m_launcherUrls;
    QHash<QString, int> m_pids;
    QStringList m_runningApps;
    QStringList m_activeApps;
    int m_sequence = 0;
    int m_rowCount = 0;
};
