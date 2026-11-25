#pragma once

#include <QString>
#include <QStringList>
#include <QVector>

#include <algorithm>

// Bounded, fail-closed application-name search for the Classic launcher.
//
// Header-only and dependency-light: it needs QtCore only, holds no state,
// launches nothing, opens no files and does no polling. It mirrors the live
// QML filtering contract in LauncherOverlay.qml so a host caller can apply
// the same case-insensitive match, bounds and selection rules off the QML
// thread. Invalid, empty or oversized input never yields a match claim.
class LauncherModel final {
public:
    static constexpr int MaxQueryChars = 128;
    static constexpr int MaxNameChars = 256;
    static constexpr int MaxCandidates = 4096;
    static constexpr int MaxResults = 64;
    static constexpr int NoSelection = -1;

    enum class State { Rejected, Browse, Search };

    struct Match {
        QString name;
        int score = 0;
        int index = 0;
    };

    struct View {
        State state = State::Rejected;
        QString key;
        QVector<Match> results;
        int selectedIndex = NoSelection;

        int count() const { return results.size(); }
        QString selectedName() const
        {
            if (selectedIndex < 0 || selectedIndex >= count())
                return QString();
            return results.at(selectedIndex).name;
        }
        QString accessibleResultCount() const
        {
            if (state == State::Rejected || count() == 0)
                return QStringLiteral("No matching applications");
            const QString prefix = QString::number(count()) +
                                   QStringLiteral(" ");
            if (state == State::Browse)
                return prefix + (count() == 1 ? QStringLiteral("application")
                                              : QStringLiteral("applications"));
            return prefix + (count() == 1 ? QStringLiteral("matching application")
                                          : QStringLiteral("matching applications"));
        }
    };

    static bool validName(const QString &name)
    {
        if (name.isEmpty() || name.size() > MaxNameChars)
            return false;
        return readable(name);
    }

    // Catalogue browsing is explicit and never a search match: an empty
    // query means "show the approved catalogue", not "every title matched".
    static View browse(const QStringList &names)
    {
        View view;
        if (!validCandidates(names))
            return view;
        view.state = State::Browse;
        for (int i = 0; i < names.size(); ++i)
            view.results.append(Match{names.at(i), 0, i});
        if (!view.results.isEmpty())
            view.selectedIndex = 0;
        return view;
    }

    // Case-insensitive substring filter. Empty, oversized, malformed or
    // wrong-shaped input returns a Rejected view with zero results.
    static View filter(const QString &query, const QStringList &names,
                       int limit = MaxResults)
    {
        View view;
        if (limit < 1 || limit > MaxResults || !validCandidates(names))
            return view;
        if (query.isEmpty() || query.size() > MaxQueryChars
            || !readable(query))
            return view;
        const QString trimmed = query.trimmed();
        if (trimmed.isEmpty())
            return view;

        const QString key = trimmed.toCaseFolded();
        if (key.isEmpty() || key.size() > MaxQueryChars * 4)
            return view;

        QVector<Match> ranked;
        for (int i = 0; i < names.size(); ++i) {
            const QString name = names.at(i);
            const QString folded = name.toCaseFolded();
            int score = 0;
            if (folded == key)
                score = 3;
            else if (folded.startsWith(key))
                score = 2;
            else if (folded.contains(key))
                score = 1;
            if (score > 0)
                ranked.append(Match{name, score, i});
        }
        std::stable_sort(ranked.begin(), ranked.end(),
                         [](const Match &a, const Match &b) {
                             return a.score > b.score;
                         });
        if (ranked.size() > limit)
            ranked.resize(limit);

        view.state = State::Search;
        view.key = key;
        view.results = ranked;
        if (!view.results.isEmpty())
            view.selectedIndex = 0;
        return view;
    }

    static View select(const View &view, int index)
    {
        View copy = view;
        copy.selectedIndex = (index >= 0 && index < copy.count())
                             ? index : NoSelection;
        return copy;
    }

    static View move(const View &view, int delta)
    {
        View copy = view;
        if (copy.count() == 0) {
            copy.selectedIndex = NoSelection;
            return copy;
        }
        const int base = (copy.selectedIndex >= 0
                          && copy.selectedIndex < copy.count())
                         ? copy.selectedIndex : 0;
        copy.selectedIndex = std::max(0, std::min(base + delta,
                                                  copy.count() - 1));
        return copy;
    }

private:
    static bool readable(const QString &text)
    {
        for (int i = 0; i < text.size(); ++i) {
            const QChar character = text.at(i);
            const ushort code = character.unicode();
            if (character.isSurrogate() || code < 0x20 || code == 0x7f)
                return false;
        }
        return true;
    }

    static bool validCandidates(const QStringList &names)
    {
        if (names.size() > MaxCandidates)
            return false;
        for (int i = 0; i < names.size(); ++i) {
            if (!validName(names.at(i)))
                return false;
        }
        return true;
    }
};
