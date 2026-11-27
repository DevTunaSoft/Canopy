#pragma once

#include <QAbstractListModel>
#include <QDir>
#include <QFileInfo>
#include <QHash>
#include <QString>
#include <QStringList>
#include <QVector>
#include <QtQml>

// Bounded, home-scoped directory listing for the Classic Files window.
// Listing happens synchronously only when navigate()/goBack()/goForward()/
// goUp()/setSearch() change state. No timers, polling, workers, network or
// process execution.
class FileModel : public QAbstractListModel
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(QString currentPath READ currentPath NOTIFY currentPathChanged)
    Q_PROPERTY(QString currentName READ currentName NOTIFY currentPathChanged)
    Q_PROPERTY(QString homePath READ homePath CONSTANT)
    Q_PROPERTY(QString searchQuery READ searchQuery WRITE setSearch NOTIFY searchQueryChanged)
    Q_PROPERTY(bool canGoBack READ canGoBack NOTIFY navigationChanged)
    Q_PROPERTY(bool canGoUp READ canGoUp NOTIFY navigationChanged)
    Q_PROPERTY(bool canGoForward READ canGoForward NOTIFY navigationChanged)
    Q_PROPERTY(int maxEntries READ maxEntries CONSTANT)
    Q_PROPERTY(int entryCount READ entryCount NOTIFY entriesChanged)
    // Fixed dock label used by the Files window's native launch action.
    // The model never stores or forwards a path, URL or caller-supplied text.
    Q_PROPERTY(QString fileManagerDockName READ fileManagerDockName CONSTANT)

public:
    enum Role {
        NameRole = Qt::UserRole + 1,
        PathRole,
        IsDirRole,
        SizeRole
    };
    Q_ENUM(Role)

    explicit FileModel(QObject *parent = nullptr);

    int rowCount(const QModelIndex &parent = QModelIndex()) const override;
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QHash<int, QByteArray> roleNames() const override;

    QString currentPath() const { return m_currentPath; }
    QString currentName() const;
    QString homePath() const { return m_homePath; }
    QString searchQuery() const { return m_searchQuery; }
    bool canGoBack() const { return !m_backStack.isEmpty(); }
    bool canGoUp() const;
    bool canGoForward() const { return !m_forwardStack.isEmpty(); }
    int maxEntries() const { return kMaxEntries; }
    int entryCount() const { return m_visible.size(); }
    // Exact, case-sensitive dock-label validation. Only the fixed "Files"
    // label passes; paths, URLs and arbitrary strings are refused here.
    QString fileManagerDockName() const { return QStringLiteral("Files"); }
    Q_INVOKABLE bool isFileManagerDockName(const QString &candidate) const
    {
        return candidate.compare(QStringLiteral("Files"), Qt::CaseSensitive) == 0;
    }

    Q_INVOKABLE bool navigate(const QString &path);
    Q_INVOKABLE bool goBack();
    Q_INVOKABLE bool goForward();
    Q_INVOKABLE bool goUp();
    Q_INVOKABLE void setSearch(const QString &text);

signals:
    void currentPathChanged();
    void searchQueryChanged();
    void navigationChanged();
    void entriesChanged();
    void navigationRejected(const QString &reason);

private:
    struct Entry {
        QString name;
        QString path;
        bool isDir = false;
        qint64 size = 0;
    };

    static constexpr int kMaxEntries = 500;
    static constexpr int kMaxHistory = 64;

    static void pushBounded(QStringList &stack, const QString &path);
    QString resolveUnderHome(const QString &path) const;
    void reload();
    void applySearch();
    void takePath(const QString &canonicalPath);

    QString m_homePath;
    QString m_currentPath;
    QString m_searchQuery;
    QStringList m_backStack;
    QStringList m_forwardStack;
    QVector<Entry> m_all;
    QVector<Entry> m_visible;
};
