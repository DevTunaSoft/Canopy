import QtQuick

// Original Canopy landscape, drawn once on exposure or resizing. No network
// assets, shaders, polling, animation loops, background services, or timers.
// The Canvas uses a single image backing store; profile its memory on Mint.
Item {
    id: wallpaper
    objectName: "canopyWallpaper"
    Accessible.name: "Original lakeside mountain landscape wallpaper"

    Canvas {
        id: painting
        anchors.fill: parent
        renderTarget: Canvas.Image
        antialiasing: true
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            const ctx = getContext("2d")
            const w = width
            const h = height
            if (w < 1 || h < 1)
                return
            ctx.clearRect(0, 0, w, h)

            function linear(y0, y1, colors) {
                const gradient = ctx.createLinearGradient(0, y0, 0, y1)
                for (let i = 0; i < colors.length; i++)
                    gradient.addColorStop(colors[i][0], colors[i][1])
                return gradient
            }
            function polygon(tone, coordinates) {
                ctx.fillStyle = tone
                ctx.beginPath()
                ctx.moveTo(coordinates[0][0] * w, coordinates[0][1] * h)
                for (let i = 1; i < coordinates.length; i++)
                    ctx.lineTo(coordinates[i][0] * w, coordinates[i][1] * h)
                ctx.closePath()
                ctx.fill()
            }
            // Airy sky with sunlight behind mountain layers.
            ctx.fillStyle = linear(0, h, [
                [0, "#82a9c0"], [0.36, "#c5d7da"],
                [0.70, "#f1d9c9"], [1, "#e3d2c5"]
            ])
            ctx.fillRect(0, 0, w, h)

            const sun = ctx.createRadialGradient(0.72*w, 0.38*h, 0,
                                                 0.72*w, 0.38*h, 0.46*w)
            sun.addColorStop(0, "rgba(255,242,210,0.80)")
            sun.addColorStop(0.23, "rgba(255,218,192,0.37)")
            sun.addColorStop(1, "rgba(255,218,192,0)")
            ctx.fillStyle = sun
            ctx.fillRect(0, 0, w, h)

            // Hazy distant terrain and illuminated snowy ridges.
            polygon("#bccbd0", [[0,0.58],[0.09,0.51],[0.18,0.56],[0.31,0.42],
                [0.44,0.52],[0.56,0.44],[0.71,0.55],[0.82,0.49],[1,0.61],[1,1],[0,1]])
            polygon("#e8eff0", [[0.14,0.56],[0.31,0.42],[0.39,0.49],
                [0.35,0.47],[0.31,0.45],[0.26,0.50],[0.21,0.52]])
            polygon("#879ca9", [[0,0.61],[0.10,0.54],[0.17,0.61],[0.34,0.43],
                [0.49,0.62],[0.67,0.47],[0.86,0.60],[1,0.54],[1,1],[0,1]])
            polygon("#dbe8e9", [[0.21,0.56],[0.34,0.43],[0.39,0.51],
                [0.35,0.48],[0.33,0.49],[0.30,0.47],[0.25,0.55]])
            polygon("#c0d3d8", [[0.57,0.57],[0.67,0.47],[0.74,0.54],
                [0.69,0.51],[0.66,0.50],[0.62,0.53]])
            polygon("#627e8f", [[0,0.72],[0.11,0.57],[0.23,0.66],[0.39,0.55],
                [0.49,0.67],[0.63,0.59],[0.75,0.67],[0.87,0.57],
                [1,0.67],[1,1],[0,1]])

            // Still water begins at the foothills. A few deterministic highlights
            // create depth without frame-by-frame rendering or noise textures.
            ctx.fillStyle = linear(0.65*h, h, [
                [0, "#96b5b8"], [0.29, "#739aa5"],
                [0.68, "#548391"], [1, "#3f7181"]
            ])
            ctx.fillRect(0, 0.665*h, w, 0.335*h)
            ctx.strokeStyle = "rgba(232,240,230,0.25)"
            for (let i = 0; i < 24; i++) {
                const yy = (0.69 + i * 0.013) * h
                const xx = ((i * 37) % 71) / 100 * w
                const lineWidth = (0.06 + (i % 5) * 0.017) * w
                ctx.lineWidth = 0.65 + (i % 3) * 0.25
                ctx.beginPath()
                ctx.moveTo(xx, yy)
                ctx.lineTo(Math.min(w, xx + lineWidth), yy)
                ctx.stroke()
            }

            // Foreground silhouette frames the vista and stays subtle behind UI.
            polygon("#3e6270", [[0,0.56],[0.07,0.65],[0.10,0.76],
                [0.17,0.84],[0.19,1],[0,1]])
            polygon("#466875", [[1,0.52],[0.94,0.64],[0.90,0.75],
                [0.87,0.83],[0.83,1],[1,1]])
            polygon("#315562", [[0,0.87],[0.10,0.92],[0.27,1],[0,1]])
            polygon("#315562", [[1,0.85],[0.92,0.91],[0.78,1],[1,1]])
        }
    }
}
