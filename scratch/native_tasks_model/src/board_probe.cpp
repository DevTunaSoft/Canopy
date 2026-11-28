#include "NativeTaskBoard.h"

#include <QCoreApplication>
#include <QDebug>
#include <QHash>
#include <QByteArray>
#include <QVariant>
#include <QUrl>
#include <QAbstractListModel>

namespace {
struct Row {
    QString appId;
    QString launcherUrl;
    int pid = 0;
    bool isWindow = false;
    bool isActive = false;
};

class FakeUpstream final : public QAbstractListModel {
public:
    enum Role {
        AppId = Qt::UserRole + 1,
        AppPid,
        IsWindow,
        IsActive,
        LauncherUrl,
        Display
    };

    QHash<int, QByteArray> roleNames() const override
    {
        return {{AppId, "appId"}, {AppPid, "appPid"}, {IsWindow, "isWindow"},
                {IsActive, "isActive"}, {LauncherUrl, "launcherUrl"},
                {Display, "display"}};
    }
    int rowCount(const QModelIndex &) const override { return m_rows.size(); }
    QVariant data(const QModelIndex &index, int role) const override
    {
        if (!index.isValid() || index.row() < 0 || index.row() >= m_rows.size())
            return QVariant();
        const Row &row = m_rows.at(index.row());
        switch (role) {
        case AppId: return row.appId;
        case AppPid: return row.pid;
        case IsWindow: return row.isWindow;
        case IsActive: return row.isActive;
        case LauncherUrl: return QUrl(row.launcherUrl);
        case Display: return row.appId;
        default: return QVariant();
        }
    }
    void append(const Row &row)
    {
        beginInsertRows(QModelIndex(), m_rows.size(), m_rows.size());
        m_rows.append(row);
        endInsertRows();
    }
    void clear()
    {
        beginResetModel();
        m_rows.clear();
        endResetModel();
    }
private:
    QVector<Row> m_rows;
};

bool check(bool ok, const char *name)
{
    qInfo().noquote() << (ok ? "BOARD_PASS " : "BOARD_FAIL ") << name;
    return ok;
}
} // namespace

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    bool ok = true;
    NativeTaskBoard board;
    FakeUpstream upstream;

    ok &= check(board.attachModel(&upstream), "single upstream model attaches");

    Row window{QStringLiteral("org.kde.konsole.desktop"),
               QStringLiteral("file:///usr/share/applications/org.kde.konsole.desktop"),
               4242, true, false};
    upstream.append(window);
    ok &= check(board.isRunning(QStringLiteral("org.kde.konsole"))
                && !board.isActive(QStringLiteral("org.kde.konsole"))
                && board.rowFor(QStringLiteral("org.kde.konsole")) == 0
                && board.runningApps() == QStringList{QStringLiteral("org.kde.konsole")},
                "window row yields bounded running indicator");

    FakeUpstream second;
    second.append(window);
    ok &= check(!board.attachModel(&second)
                && board.rowFor(QStringLiteral("org.kde.konsole")) == 0,
                "second authoritative model refused");

    Row launcher{QStringLiteral("org.kde.dolphin"),
                 QStringLiteral("file:///usr/share/applications/org.kde.dolphin.desktop"),
                 0, false, false};
    upstream.append(launcher);
    ok &= check(!board.isRunning(QStringLiteral("org.kde.dolphin"))
                && board.launcherRowFor(QStringLiteral("org.kde.dolphin")) == 1
                && board.launcherUrlFor(QStringLiteral("org.kde.dolphin"))
                       .contains(QStringLiteral("dolphin.desktop")),
                "launcher row is not a running claim");

    upstream.clear();
    ok &= check(!board.isRunning(QStringLiteral("org.kde.konsole"))
                && board.rowFor(QStringLiteral("org.kde.konsole")) < 0,
                "window removal clears indicator");

    Row active{QStringLiteral("org.kde.konsole.desktop"),
               QStringLiteral("file:///usr/share/applications/org.kde.konsole.desktop"),
               4243, true, true};
    upstream.append(active);
    ok &= check(board.isActive(QStringLiteral("org.kde.konsole"))
                && board.snapshotJson().contains(QStringLiteral("injected_upstream_only")),
                "active row and deterministic snapshot");

    board.detachModel();
    ok &= check(!board.isRunning(QStringLiteral("org.kde.konsole"))
                && !board.attached()
                && !board.attachModel(static_cast<QAbstractItemModel *>(nullptr)),
                "detach fails closed and refuses null model");

    qInfo().noquote() << (ok ? "BOARD_ALL_PASS" : "BOARD_ALL_FAIL");
    return ok ? 0 : 1;
}
