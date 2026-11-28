#include "NativeTaskBoard.h"

#include <QAbstractItemModel>
#include <QDebug>
#include <QHash>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMetaType>
#include <QModelIndex>
#include <QUrl>
#include <QVariant>

QString NativeTaskBoard::canonicalId(const QString &raw)
{
    QString id = raw.trimmed();
    static const QString suffix = QStringLiteral(".desktop");
    if (id.endsWith(suffix, Qt::CaseInsensitive))
        id.chop(suffix.size());
    if (id.isEmpty() || id.size() > kMaxIdChars)
        return QString();
    for (int i = 0; i < id.size(); ++i) {
        const ushort code = id.at(i).unicode();
        const bool alnum = (code >= 'a' && code <= 'z')
            || (code >= 'A' && code <= 'Z') || (code >= '0' && code <= '9');
        if (!alnum && code != '.' && code != '_' && code != '-')
            return QString();
    }
    return id.toLower();
}

bool NativeTaskBoard::resolveRoles(QAbstractItemModel *model, Roles *out)
{
    if (!model || !out)
        return false;
    const QHash<int, QByteArray> names = model->roleNames();
    // Plasma 6 publishes enum-style role names (AppId, IsWindow, ...), while
    // some Qt models use camelCase. Accept both; never guess a numeric id.
    auto find = [&names](const char *primary, const char *alternate,
                         int *target) {
        for (auto it = names.constBegin(); it != names.constEnd(); ++it) {
            if (it.value() == QByteArray(primary)
                    || (alternate && it.value() == QByteArray(alternate))) {
                *target = it.key();
                return true;
            }
        }
        return false;
    };
    if (!find("AppId", "appId", &out->appId)
            || !find("IsWindow", "isWindow", &out->isWindow)
            || !find("IsActive", "isActive", &out->isActive)
            || !find("LauncherUrl", "launcherUrl", &out->launcherUrl))
        return false;
    find("AppPid", "appPid", &out->appPid);
    find("display", "Display", &out->display);
    return true;
}

QVariant NativeTaskBoard::roleData(QAbstractItemModel *model, int row,
                                   int role, const QModelIndex &parent)
{
    if (!model || role < 0)
        return QVariant();
    return model->data(model->index(row, 0, parent), role);
}

NativeTaskBoard::NativeTaskBoard(QObject *parent) : QObject(parent) {}

NativeTaskBoard::~NativeTaskBoard()
{
    disconnectModel();
}

void NativeTaskBoard::connectModel(QAbstractItemModel *model)
{
    connect(model, &QAbstractItemModel::modelReset,
            this, &NativeTaskBoard::rebuild);
    connect(model, &QAbstractItemModel::layoutChanged,
            this, [this]() { rebuild(); });
    connect(model, &QAbstractItemModel::rowsInserted,
            this, [this](const QModelIndex &, int, int) { rebuild(); });
    connect(model, &QAbstractItemModel::rowsRemoved,
            this, [this](const QModelIndex &, int, int) { rebuild(); });
    connect(model, &QAbstractItemModel::dataChanged,
            this, [this](const QModelIndex &, const QModelIndex &,
                         const QList<int> &) { rebuild(); });
    connect(model, &QObject::destroyed,
            this, [this]() {
                if (m_model) {
                    m_model = nullptr;
                    clearFailClosed();
                }
            });
}

void NativeTaskBoard::disconnectModel()
{
    if (m_model)
        disconnect(m_model, nullptr, this, nullptr);
}

void NativeTaskBoard::clearFailClosed()
{
    m_windowRows.clear();
    m_launcherRows.clear();
    m_launcherUrls.clear();
    m_pids.clear();
    m_runningApps.clear();
    m_activeApps.clear();
    m_rowCount = 0;
    ++m_sequence;
    emit stateChanged();
}

bool NativeTaskBoard::attachModel(QObject *modelObject)
{
    auto *candidate = qobject_cast<QAbstractItemModel *>(modelObject);
    if (!candidate) {
        logEvent(QStringLiteral("REFUSE model is not QAbstractItemModel"));
        return false;
    }
    if (m_model && m_model != candidate) {
        // PR #730: exactly one authoritative TasksModel. A second injection
        // is a conflict, never a replacement.
        logEvent(QStringLiteral("REFUSE second authoritative model"));
        return false;
    }
    if (m_model == candidate)
        return true;

    Roles roles;
    if (!resolveRoles(candidate, &roles)) {
        QStringList published;
        const QHash<int, QByteArray> names = candidate->roleNames();
        for (auto it = names.constBegin(); it != names.constEnd(); ++it)
            published.append(QString::fromUtf8(it.value()));
        published.sort();
        logEvent(QStringLiteral("REFUSE missing upstream role; published=%1")
                     .arg(published.join(QLatin1Char(','))));
        return false;
    }
    m_model = candidate;
    m_roles = roles;
    connectModel(m_model);
    rebuild();
    return true;
}

void NativeTaskBoard::detachModel()
{
    if (!m_model)
        return;
    disconnectModel();
    m_model = nullptr;
    clearFailClosed();
}

void NativeTaskBoard::rebuild()
{
    if (!m_model) {
        clearFailClosed();
        return;
    }
    const int count = m_model->rowCount(QModelIndex());
    if (count < 0 || count > kMaxRows) {
        clearFailClosed();
        return;
    }

    QHash<QString, int> windowRows;
    QHash<QString, int> launcherRows;
    QHash<QString, QString> launcherUrls;
    QHash<QString, int> pids;
    QStringList running;
    QStringList active;

    for (int row = 0; row < count; ++row) {
        const QModelIndex parent;
        const QVariant isWindowVar = roleData(m_model, row, m_roles.isWindow, parent);
        const QVariant isActiveVar = roleData(m_model, row, m_roles.isActive, parent);
        if (isWindowVar.typeId() != QMetaType::Bool
                || isActiveVar.typeId() != QMetaType::Bool)
            continue;  // an unknown row is not a running-app claim
        const bool isWindow = isWindowVar.toBool();
        const bool isActive = isActiveVar.toBool();

        QString appIdKey;
        const QVariant appVar = roleData(m_model, row, m_roles.appId, parent);
        if (appVar.typeId() == QMetaType::QString)
            appIdKey = canonicalId(appVar.toString());
        const QVariant urlVar = roleData(m_model, row, m_roles.launcherUrl, parent);
        QString launcherUrl;
        QString urlId;
        if (urlVar.typeId() == QMetaType::QUrl
                || urlVar.typeId() == QMetaType::QString) {
            const QUrl url = urlVar.toUrl();
            launcherUrl = url.toString(QUrl::FullyEncoded);
            if (url.isLocalFile())
                urlId = canonicalId(url.fileName());
        }
        // Dock favorites are desktop ids. Upstream windows often carry a bare
        // WM_CLASS in AppId, so prefer the launcher id and keep the raw AppId
        // only as an alias for the same live row.
        QString id = urlId.isEmpty() ? appIdKey : urlId;

        if (isWindow) {
            if (id.isEmpty()) {
                clearFailClosed();
                return;
            }
            if (m_roles.appPid >= 0) {
                const QVariant pidVar = roleData(m_model, row, m_roles.appPid, parent);
                int pid = 0;
                if (pidVar.typeId() == QMetaType::Int
                        || pidVar.typeId() == QMetaType::LongLong) {
                    const qlonglong value = pidVar.toLongLong();
                    if (value >= 0 && value <= kMaxPid)
                        pid = static_cast<int>(value);
                }
                if (pid > 0)
                    pids.insert(id, pid);
            }
            if (!windowRows.contains(id))
                windowRows.insert(id, row);
            if (!appIdKey.isEmpty() && appIdKey != id
                    && !windowRows.contains(appIdKey))
                windowRows.insert(appIdKey, row);
            if (!running.contains(id))
                running.append(id);
            if (isActive && !active.contains(id))
                active.append(id);
        } else if (!id.isEmpty()) {
            if (!launcherRows.contains(id))
                launcherRows.insert(id, row);
            if (!launcherUrls.contains(id) && !launcherUrl.isEmpty())
                launcherUrls.insert(id, launcherUrl);
        }
    }

    running.sort();
    active.sort();
    m_windowRows = windowRows;
    m_launcherRows = launcherRows;
    m_launcherUrls = launcherUrls;
    m_pids = pids;
    m_runningApps = running;
    m_activeApps = active;
    m_rowCount = count;
    if (m_sequence >= kMaxSequence)
        m_sequence = 0;
    ++m_sequence;
    emit stateChanged();
    qInfo().noquote() << "CANOPY_NATIVE_TASK_SNAPSHOT" << snapshotJson();
}

bool NativeTaskBoard::isRunning(const QString &appId) const
{
    return m_windowRows.contains(canonicalId(appId));
}

bool NativeTaskBoard::isActive(const QString &appId) const
{
    return m_activeApps.contains(canonicalId(appId));
}

int NativeTaskBoard::rowFor(const QString &appId) const
{
    return m_windowRows.value(canonicalId(appId), -1);
}

int NativeTaskBoard::launcherRowFor(const QString &appId) const
{
    return m_launcherRows.value(canonicalId(appId), -1);
}

QString NativeTaskBoard::launcherUrlFor(const QString &appId) const
{
    return m_launcherUrls.value(canonicalId(appId));
}

QString NativeTaskBoard::snapshotJson() const
{
    QJsonObject out;
    out.insert(QStringLiteral("schema"), 1);
    out.insert(QStringLiteral("attached"), attached());
    out.insert(QStringLiteral("sequence"), m_sequence);
    out.insert(QStringLiteral("row_count"), m_rowCount);
    out.insert(QStringLiteral("running"), QJsonArray::fromStringList(m_runningApps));
    out.insert(QStringLiteral("active"), QJsonArray::fromStringList(m_activeApps));
    out.insert(QStringLiteral("model_source"), QStringLiteral("injected_upstream_only"));
    return QString::fromUtf8(QJsonDocument(out).toJson(QJsonDocument::Compact));
}

void NativeTaskBoard::logEvent(const QString &event)
{
    qInfo().noquote() << "CANOPY_NATIVE_TASK_EVENT" << event;
}
