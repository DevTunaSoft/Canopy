import QtQuick

// Original, resolution-independent illustrated landscape.
// One Canvas backing store, repainted on resize; no timers, motion, effects or services.
Canvas {
    id: landscape
    objectName: "canopyLandscape"
    renderTarget: Canvas.Image
    antialiasing: true
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const c = getContext("2d")
        const w = width
        const h = height
        if (w <= 0 || h <= 0)
            return
        c.reset()
        c.save()
        c.scale(w, h)

        // Light, airy mountain morning; authored specifically for Canopy.
        let sky = c.createLinearGradient(0, 0, 0, 1)
        sky.addColorStop(0, "#a9c9de")
        sky.addColorStop(0.43, "#d6e6ee")
        sky.addColorStop(0.72, "#f6e9dc")
        sky.addColorStop(1, "#e5e5e2")
        c.fillStyle = sky
        c.fillRect(0, 0, 1, 1)

        // Warm horizon glow: static radial gradient in the raster cache.
        let glow = c.createRadialGradient(0.77, 0.45, 0.01, 0.77, 0.45, 0.42)
        glow.addColorStop(0, "rgba(255,246,223,0.68)")
        glow.addColorStop(1, "rgba(255,246,223,0)")
        c.fillStyle = glow
        c.fillRect(0, 0, 1, 1)

        function mountain(color, points) {
            c.beginPath()
            c.moveTo(0, 1)
            for (let i = 0; i < points.length; i++)
                c.lineTo(points[i][0], points[i][1])
            c.lineTo(1, 1)
            c.closePath()
            c.fillStyle = color
            c.fill()
        }

        mountain("#cedbe0", [[0,0.68],[0.10,0.57],[0.20,0.65],[0.34,0.45],
            [0.45,0.60],[0.57,0.51],[0.70,0.66],[0.83,0.49],[1,0.66]])
        mountain("#afc6cf", [[0,0.76],[0.11,0.70],[0.24,0.55],[0.34,0.71],
            [0.48,0.58],[0.59,0.72],[0.73,0.56],[0.88,0.70],[1,0.60]])
        mountain("#799eaa", [[0,0.87],[0.16,0.75],[0.28,0.85],[0.42,0.69],
            [0.59,0.83],[0.75,0.71],[0.88,0.83],[1,0.76]])
        mountain("#587d87", [[0,0.94],[0.16,0.88],[0.27,0.96],[0.41,0.81],
            [0.56,0.92],[0.68,0.83],[0.83,0.93],[1,0.86]])

        // Foreground lake uses flat shapes with a restrained surface highlight.
        let water = c.createLinearGradient(0, 0.86, 0, 1)
        water.addColorStop(0, "#7da4ad")
        water.addColorStop(1, "#476d7b")
        c.fillStyle = water
        c.beginPath()
        c.moveTo(0, 0.93)
        c.bezierCurveTo(0.26, 0.89, 0.49, 0.95, 0.72, 0.91)
        c.bezierCurveTo(0.85, 0.89, 0.94, 0.92, 1, 0.91)
        c.lineTo(1, 1)
        c.lineTo(0, 1)
        c.closePath()
        c.fill()
        c.strokeStyle = "rgba(225,240,239,0.28)"
        c.lineWidth = 0.0016
        for (let i = 0; i < 8; i++) {
            const y = 0.94 + i * 0.007
            c.beginPath()
            c.moveTo(0.36 - (i % 3) * 0.045, y)
            c.lineTo(0.62 + (i % 2) * 0.075, y)
            c.stroke()
        }
        c.restore()
    }
}
