#pragma once

#include <QHash>
#include <QImage>
#include <QQuickImageProvider>
#include <QString>

// All eight verified original PNGs stay untouched on disk. Once after source
// verification, this provider renders padded, antialiased, rounded previews
// into a small fixed cache; no shader, per-frame crop, or polling loop.
class RoundedDockIconProvider final : public QQuickImageProvider {
public:
    explicit RoundedDockIconProvider(const QString &approvedRoot,
                                     const QString &terminalCandidatePath,
                                     bool framingReviewMode, QString *error);

    bool isValid() const { return m_images.size() == 8; }
    bool allCornersClipped() const;
    QImage requestImage(const QString &id, QSize *size,
                        const QSize &requestedSize) override;

private:
    QHash<QString, QImage> m_images;
};
