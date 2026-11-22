#include "FileModel.h"

#include <QDirIterator>
#include <QFileInfo>

namespace {
#ifdef Q_OS_WIN
const Qt::CaseSensitivity kCase = Qt::CaseInsensitive;
#else
const Qt::CaseSensitivity kCase = Qt::CaseSensitive;
#endif
} // namespace

FileModel::FileModel(QObject *parent)
    : QAbstractListModel(parent)
{
    const QString rawHome = QDir::homePath();
    const QFileInfo homeInfo(rawHome);
    m_homePath = homeInfo.exists() ? homeInfo.canonicalFilePath() : rawHome;
    m_currentPath = m_homePath;
    reload();
}

int FileModel::rowCount(const QModelIndex &parent) const
{
    return parent.isValid() ? 0 : m_visible.size();
}

QVariant FileModel::data(const QModelIndex &index, int role) const
{
    if (!index.isValid() || index.row() < 0 || index.row() >= m_visible.size())
        return QVariant();
    const Entry &entry = m_visible.at(index.row());
    switch (role) {
    case NameRole:  return entry.name;
    case PathRole:  return entry.path;
    case IsDirRole: return entry.isDir;
    case SizeRole:  return entry.size;
    default:        return QVariant();
    }
}

QHash<int, QByteArray> FileModel::roleNames() const
{
    return {
        { NameRole,  "name" },
        { PathRole,  "path" },
        { IsDirRole, "isDir" },
        { SizeRole,  "size" }
    };
}

QString FileModel::currentName() const
{
    if (m_currentPath.compare(m_homePath, kCase) == 0)
        return QStringLiteral("Home");
    return QFileInfo(m_currentPath).fileName();
}

bool FileModel::canGoUp() const
{
    QDir parent(m_currentPath);
    if (!parent.cdUp())
        return false;
    return !resolveUnderHome(parent.absolutePath()).isEmpty();
}

bool FileModel::navigate(const QString &path)
{
    const QString target = resolveUnderHome(path);
    if (target.isEmpty()) {
        emit navigationRejected(QStringLiteral("path outside home or unreadable"));
        return false;
    }
    if (!QFileInfo(target).isDir()) {
        emit navigationRejected(QStringLiteral("not a directory"));
        return false;
    }
    if (target.compare(m_currentPath, kCase) == 0)
        return true;
    m_backStack.append(m_currentPath);
    takePath(target);
    return true;
}

bool FileModel::goBack()
{
    if (m_backStack.isEmpty())
        return false;
    const QString target = m_backStack.takeLast();
    takePath(target);
    return true;
}

bool FileModel::goUp()
{
    QDir parent(m_currentPath);
    if (!parent.cdUp())
        return false;
    const QString target = resolveUnderHome(parent.absolutePath());
    if (target.isEmpty() || target.compare(m_currentPath, kCase) == 0) {
        emit navigationRejected(QStringLiteral("path outside home"));
        return false;
    }
    m_backStack.append(m_currentPath);
    takePath(target);
    return true;
}

void FileModel::setSearch(const QString &text)
{
    if (text == m_searchQuery)
        return;
    m_searchQuery = text;
    beginResetModel();
    applySearch();
    endResetModel();
    emit searchQueryChanged();
    emit entriesChanged();
}

QString FileModel::resolveUnderHome(const QString &path) const
{
    QString candidate = path.trimmed();
    if (candidate.isEmpty())
        candidate = m_homePath;
    const QFileInfo info(candidate);
    if (!info.exists())
        return QString();
    const QString canonical = info.canonicalFilePath();
    if (canonical.isEmpty())
        return QString();
    if (canonical.compare(m_homePath, kCase) == 0)
        return canonical;
    const QString prefix = m_homePath.endsWith(QLatin1Char('/'))
        ? m_homePath : m_homePath + QLatin1Char('/');
    if (!canonical.startsWith(prefix, kCase))
        return QString();
    return canonical;
}

void FileModel::takePath(const QString &canonicalPath)
{
    m_currentPath = canonicalPath;
    reload();
    emit currentPathChanged();
    emit navigationChanged();
}

void FileModel::reload()
{
    beginResetModel();
    m_all.clear();
    m_visible.clear();

    // One synchronous, non-recursive pass. Stop at the cap so a large home
    // directory cannot grow RAM or enumerate more than kMaxEntries entries.
    QDirIterator it(m_currentPath,
                    QDir::NoDotAndDotDot | QDir::AllEntries | QDir::Readable,
                    QDirIterator::NoIteratorFlags);
    while (it.hasNext() && m_all.size() < kMaxEntries) {
        const QFileInfo info = it.next();
        Entry entry;
        entry.name = info.fileName();
        entry.path = info.absoluteFilePath();
        entry.isDir = info.isDir();
        entry.size = info.isFile() ? info.size() : 0;
        m_all.append(entry);
    }
    applySearch();
    endResetModel();
    emit entriesChanged();
}

void FileModel::applySearch()
{
    m_visible.clear();
    const QString needle = m_searchQuery.trimmed().toLower();
    for (const Entry &entry : m_all) {
        if (needle.isEmpty() || entry.name.toLower().contains(needle))
            m_visible.append(entry);
    }
}
