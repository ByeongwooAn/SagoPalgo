$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Drawing

$resources = Join-Path $PSScriptRoot '../windows/runner/resources'
$previewPath = Join-Path $resources 'app_icon.png'
$iconPath = Join-Path $resources 'app_icon.ico'
$sizes = @(16, 24, 32, 48, 64, 128, 256)
$frames = [System.Collections.Generic.List[byte[]]]::new()

foreach ($size in $sizes) {
    $bitmap = [System.Drawing.Bitmap]::new($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $backgroundPath = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $chartPath = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $gradient = $null
    $whitePen = $null
    $whiteBrush = $null
    $goldBrush = $null
    $stream = [System.IO.MemoryStream]::new()

    try {
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.ScaleTransform($size / 256.0, $size / 256.0)

        # 앱의 AppTheme.main -> AppTheme.sub 그라데이션입니다.
        $backgroundPath.AddArc(8, 8, 104, 104, 180, 90)
        $backgroundPath.AddArc(144, 8, 104, 104, 270, 90)
        $backgroundPath.AddArc(144, 144, 104, 104, 0, 90)
        $backgroundPath.AddArc(8, 144, 104, 104, 90, 90)
        $backgroundPath.CloseFigure()
        $gradient = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
            [System.Drawing.RectangleF]::new(8, 8, 240, 240),
            [System.Drawing.ColorTranslator]::FromHtml('#8D17C6'),
            [System.Drawing.ColorTranslator]::FromHtml('#D44B76'),
            45.0
        )
        $graphics.FillPath($gradient, $backgroundPath)

        # 상승하는 차트와 금색 시작점은 작은 작업 표시줄 아이콘에서도 구분됩니다.
        $chartPoints = [System.Drawing.PointF[]]@(
            [System.Drawing.PointF]::new(53, 180),
            [System.Drawing.PointF]::new(105, 128),
            [System.Drawing.PointF]::new(139, 157),
            [System.Drawing.PointF]::new(194, 94)
        )
        $chartPath.AddLines($chartPoints)
        $whitePen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, 29)
        $whitePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $whitePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $whitePen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
        $graphics.DrawPath($whitePen, $chartPath)

        $whiteBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
        $arrow = [System.Drawing.PointF[]]@(
            [System.Drawing.PointF]::new(216, 65),
            [System.Drawing.PointF]::new(164, 74),
            [System.Drawing.PointF]::new(208, 117)
        )
        $graphics.FillPolygon($whiteBrush, $arrow)

        $goldBrush = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#F3A411'))
        $graphics.FillEllipse($goldBrush, 39, 166, 28, 28)

        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        $frames.Add($stream.ToArray())
        if ($size -eq 256) {
            $bitmap.Save($previewPath, [System.Drawing.Imaging.ImageFormat]::Png)
        }
    }
    finally {
        $stream.Dispose()
        if ($goldBrush) { $goldBrush.Dispose() }
        if ($whiteBrush) { $whiteBrush.Dispose() }
        if ($whitePen) { $whitePen.Dispose() }
        if ($gradient) { $gradient.Dispose() }
        $chartPath.Dispose()
        $backgroundPath.Dispose()
        $graphics.Dispose()
        $bitmap.Dispose()
    }
}

# ICO 컨테이너에 크기별 PNG 프레임을 넣습니다. 256픽셀은 ICO 규격상 0으로 표기합니다.
$file = [System.IO.File]::Open($iconPath, [System.IO.FileMode]::Create)
$writer = [System.IO.BinaryWriter]::new($file)
try {
    $writer.Write([uint16]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]$sizes.Count)
    $offset = 6 + 16 * $sizes.Count
    for ($index = 0; $index -lt $sizes.Count; $index++) {
        $dimension = if ($sizes[$index] -eq 256) { 0 } else { $sizes[$index] }
        $writer.Write([byte]$dimension)
        $writer.Write([byte]$dimension)
        $writer.Write([byte]0)
        $writer.Write([byte]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]32)
        $writer.Write([uint32]$frames[$index].Length)
        $writer.Write([uint32]$offset)
        $offset += $frames[$index].Length
    }
    foreach ($frame in $frames) {
        $writer.Write($frame)
    }
}
finally {
    $writer.Dispose()
}

Write-Output "Generated $iconPath and $previewPath"
