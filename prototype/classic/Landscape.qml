import QtQuick

// Canopy's original abstract wallpaper. One cached Canvas.Image surface,
// repainted only for initial display and actual resize (not on an idle timer).
Canvas {
    id: landscape
    objectName: "canopyLandscape"
    renderTarget: Canvas.Image
    antialiasing: true
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        const c = getContext("2d")
        if (width <= 0 || height <= 0)
            return
        c.reset()
        c.save()
        c.scale(width, height)

        let base = c.createLinearGradient(0, 0, 1, 1)
        base.addColorStop(0, "#090c36")
        base.addColorStop(0.36, "#19246a")
        base.addColorStop(0.70, "#38236d")
        base.addColorStop(1, "#07184d")
        c.fillStyle = base
        c.fillRect(0, 0, 1, 1)

        function bloom(x, y, r, inner) {
            const g = c.createRadialGradient(x, y, 0, x, y, r)
            g.addColorStop(0, inner)
            g.addColorStop(1, "rgba(17,17,60,0)")
            c.fillStyle = g
            c.fillRect(0, 0, 1, 1)
        }
        bloom(0.29, 0.52, 0.56, "rgba(221,67,173,0.43)")
        bloom(0.86, 0.35, 0.53, "rgba(148,64,226,0.47)")
        bloom(0.63, 0.88, 0.54, "rgba(49,112,246,0.47)")

        // Three original broad flowing bands, built as filled bezier ribbons.
        // No per-frame sampling, textures, blur effects or animation.
        function ribbon(points, colors) {
            const gradient = c.createLinearGradient(0, points[0][1], 1, points[1][1])
            gradient.addColorStop(0, colors[0])
            gradient.addColorStop(0.53, colors[1])
            gradient.addColorStop(1, colors[2])
            c.fillStyle = gradient
            c.beginPath()
            c.moveTo(points[0][0], points[0][1])
            c.bezierCurveTo(points[2][0], points[2][1], points[2][2], points[2][3], points[2][4], points[2][5])
            c.bezierCurveTo(points[3][0], points[3][1], points[3][2], points[3][3], points[3][4], points[3][5])
            c.bezierCurveTo(points[4][0], points[4][1], points[4][2], points[4][3], points[4][4], points[4][5])
            c.bezierCurveTo(points[5][0], points[5][1], points[5][2], points[5][3], points[5][4], points[5][5])
            c.closePath()
            c.fill()
        }

        ribbon([[0,0.18],[1,0.34],
            [0.17,0.10,0.17,0.63,0.48,0.57],
            [0.74,0.52,0.80,0.22,1,0.17],
            [1,0.34,0.76,0.76,0.53,0.73],
            [0.28,0.68,0.16,0.35,0,0.42]],
            ["#421b79","#9b3dba","#623ad7"])
        ribbon([[0,0.55],[1,0.73],
            [0.21,0.43,0.27,0.82,0.51,0.75],
            [0.78,0.68,0.84,0.43,1,0.44],
            [1,0.73,0.80,0.92,0.57,0.88],
            [0.30,0.84,0.16,0.62,0,0.72]],
            ["#151e72","#6a2db0","#284ede"])
        ribbon([[0,0.85],[1,0.95],
            [0.17,0.67,0.29,0.96,0.53,0.94],
            [0.74,0.91,0.83,0.72,1,0.79],
            [1,0.95,0.73,1.05,0.50,1.03],
            [0.26,1.01,0.16,0.87,0,1.00]],
            ["#063b95","#206ee1","#4228aa"])

        // A small soft glow along the curve is static and part of the cache.
        bloom(0.15, 0.66, 0.36, "rgba(241,88,195,0.20)")
        c.restore()
    }
}
