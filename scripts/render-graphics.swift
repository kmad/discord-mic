// Render README graphics with macOS AppKit. No extra packages required.
// swift -module-cache-path /tmp/discord-mic-swift-cache scripts/render-graphics.swift /tmp/discord-mic-frames
// Copy frame-000.png to assets/audio-flow.png for the still image.
// Build the GIF with FFmpeg:
// ffmpeg -framerate 12 -i /tmp/discord-mic-frames/frame-%03d.png -filter_complex "[0:v]split[a][b];[a]palettegen=max_colors=96:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3" -loop 0 -y assets/audio-flow.gif
import AppKit
import Foundation

let output = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "/tmp/discord-mic-frames"
try FileManager.default.createDirectory(atPath: output, withIntermediateDirectories: true)
let width = 1120, height = 440
func color(_ hex: UInt32) -> NSColor {
    NSColor(red: CGFloat((hex >> 16) & 255)/255, green: CGFloat((hex >> 8) & 255)/255, blue: CGFloat(hex & 255)/255, alpha: 1)
}
let bg = color(0x10151D), card = color(0x19222E), ink = color(0xF1F5FA)
let muted = color(0xA6B3C5), border = color(0x2B394B), green = color(0x83E8AA), purple = color(0xA7A4FF)
func box(_ x: CGFloat, _ y: CGFloat, _ w: CGFloat, _ h: CGFloat, _ r: CGFloat, _ fill: NSColor, _ stroke: NSColor? = nil) {
    let p = NSBezierPath(roundedRect: NSRect(x:x,y:y,width:w,height:h),xRadius:r,yRadius:r)
    fill.setFill(); p.fill()
    if let s = stroke { s.setStroke(); p.lineWidth = 1.5; p.stroke() }
}
func line(_ points: [(CGFloat,CGFloat)], _ c: NSColor, _ weight: CGFloat = 3) {
    let p = NSBezierPath(); p.lineWidth=weight; p.lineCapStyle = .round; p.lineJoinStyle = .round
    p.move(to:NSPoint(x:points[0].0,y:points[0].1))
    for a in points.dropFirst() { p.line(to:NSPoint(x:a.0,y:a.1)) }
    c.setStroke(); p.stroke()
}
func label(_ s:String,_ x:CGFloat,_ y:CGFloat,_ size:CGFloat,_ c:NSColor,_ bold:Bool=false,_ centered:Bool=false) {
    let attrs: [NSAttributedString.Key: Any] = [.font:NSFont.systemFont(ofSize:size,weight:bold ? .bold : .regular),.foregroundColor:c]
    let text = s as NSString
    let tw = text.size(withAttributes:attrs).width
    NSGraphicsContext.saveGraphicsState()
    let textTransform = NSAffineTransform()
    textTransform.translateX(by: centered ? x-tw/2 : x, yBy: y+text.size(withAttributes:attrs).height)
    textTransform.scaleX(by:1,yBy:-1)
    textTransform.concat()
    text.draw(at:.zero,withAttributes:attrs)
    NSGraphicsContext.restoreGraphicsState()
}
func circle(_ x: CGFloat,_ y:CGFloat,_ r:CGFloat,_ c:NSColor) { c.setFill(); NSBezierPath(ovalIn:NSRect(x:x-r,y:y-r,width:r*2,height:r*2)).fill() }
func bars(_ x:CGFloat,_ y:CGFloat,_ t:Double,_ c:NSColor) {
    for n in 0..<5 {
        let h = CGFloat(10 + 22 * abs(sin(t * 2 * .pi + Double(n)*0.9)))
        box(x+CGFloat(n)*8,y-h/2,4,h,2,c)
    }
}
for frame in 0..<48 {
    let t=Double(frame)/48
    let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:width,pixelsHigh:height,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    let ctx=NSGraphicsContext(bitmapImageRep:bitmap)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current=ctx
    let flip=NSAffineTransform(); flip.translateX(by:0,yBy:CGFloat(height)); flip.scaleX(by:1,yBy:-1); flip.concat()
    bg.setFill(); NSRect(x:0,y:0,width:width,height:height).fill()
    label("MAC AUDIO. XBOX HEADPHONES.",48,34,32,ink,true)
    label("Play on your Mac. Hear it while you game.",48,81,19,muted)
    let xs: [CGFloat] = [48,324,600,876]
    let titles=["Mac audio","Discord bot","Xbox","Headphones"]
    let subs=["Music, videos, apps","Your voice channel","Join and keep playing","Listen here"]
    for i in 0..<4 {
        let x=xs[i], cx=x+98, accent=i==1 ? purple : green
        box(x,147,196,197,20,card,border)
        if i==0 {
            box(cx-39,174,78,51,5,bg,accent)
            line([(cx-48,234),(cx+48,234)],accent,4)
            bars(cx-18,200,t,accent)
        } else if i==1 {
            box(cx-37,175,74,51,15,bg,accent)
            line([(cx-17,226),(cx-17,236),(cx-5,226)],accent,3)
            bars(cx-18,200,t-0.1,accent)
        } else if i==2 {
            box(cx-28,169,56,69,7,bg,accent)
            circle(cx+15,181,2.5,accent)
            line([(cx-13,189),(cx+13,218)],accent,3)
            line([(cx+13,189),(cx-13,218)],accent,3)
        } else {
            let p=NSBezierPath(); p.move(to:NSPoint(x:cx-31,y:211)); p.curve(to:NSPoint(x:cx+31,y:211),controlPoint1:NSPoint(x:cx-35,y:163),controlPoint2:NSPoint(x:cx+35,y:163)); p.lineWidth=5; accent.setStroke(); p.stroke()
            box(cx-37,204,13,29,5,accent)
            box(cx+24,204,13,29,5,accent)
        }
        label(titles[i],cx,259,22,ink,true,true)
        label(subs[i],cx,296,14,muted,false,true)
        if i<3 {
            let start=x+210, end=xs[i+1]-14
            line([(start,244),(end,244)],border,2)
            line([(end-6,239),(end,244),(end-6,249)],muted,2)
            // Three evenly spaced pulses make the direction clear in every loop.
            for pulse in 0..<2 {
                let phase=(t*2+Double(pulse)/2).truncatingRemainder(dividingBy:1)
                circle(start+CGFloat(phase)*(end-start-9),244,3.5,green)
            }
        }
    }
    circle(53,390,4,green)
    label("One Discord voice channel connects them all.",68,378,17,muted)
    NSGraphicsContext.restoreGraphicsState()
    let data=bitmap.representation(using:.png,properties:[:])!
    try data.write(to:URL(fileURLWithPath:String(format:"%@/frame-%03d.png",output,frame)))
}
print("Rendered 48 frames to \(output)")
