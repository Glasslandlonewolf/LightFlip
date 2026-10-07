"""Conservative raster artwork separation for local editable Office export.

The source is a raster page, so extraction cannot recover the author's original
layers. We identify bounded artwork against flat panels and reconstruct only
when the surrounding panel gives a reliable replacement. Coordinates are source
pixels; exported colors are RGB, while the input array is OpenCV BGR.
"""
from pathlib import Path
import math


def _palette(image):
    import cv2
    import numpy as np
    small = cv2.resize(image, (max(1, image.shape[1]//3), max(1, image.shape[0]//3)))
    floating = small.astype('float32')
    mean = cv2.boxFilter(floating, -1, (9, 9))
    variance = cv2.boxFilter(floating*floating, -1, (9, 9))-mean*mean
    flat = np.max(variance, axis=2) < 12
    if int(flat.sum()) < small.shape[0]*small.shape[1]*.015:
        return np.empty((0, 3), dtype='float32')
    pixels = small.reshape(-1,3)
    bins = pixels.astype('int32')//12
    codes = bins[:, 0]+bins[:, 1]*22+bins[:, 2]*22*22
    values, counts = np.unique(codes, return_counts=True)
    colors = []
    for index in np.argsort(counts)[::-1][:80]:
        if counts[index] < small.shape[0]*small.shape[1]*.0003:
            break
        bin_pixels=pixels[codes == values[index]]
        packed=bin_pixels[:,0].astype('int32')+(bin_pixels[:,1].astype('int32')<<8)+(bin_pixels[:,2].astype('int32')<<16)
        exact,frequency=np.unique(packed,return_counts=True)
        mode=frequency.argmax()
        # A thin perfectly flat frame may share its coarse color bin with a
        # large photograph. Its exact repeated color is stronger evidence than
        # that photograph's median shade.
        selected=int(exact[mode])
        mode_color=np.array([selected&255,(selected>>8)&255,(selected>>16)&255],dtype=float)
        color=mode_color if frequency[mode]>small.shape[0]*small.shape[1]*.0005 or frequency[mode]>len(bin_pixels)*.10 else np.median(bin_pixels,axis=0)
        color=np.asarray(color,dtype='float32')
        if colors and min(np.linalg.norm(color-other) for other in colors) <= 20:
            continue
        color_distance=np.linalg.norm(floating-color,axis=2)
        raw_matching=color_distance<10
        matching=raw_matching&flat
        edge_support=sum(float(part.mean())>.02 for part in
                         (matching[:2],matching[-2:],matching[:,:2],matching[:,-2:]))
        broad=False
        if matching.sum()>small.shape[0]*small.shape[1]*.002:
            count,labels,stats,_=cv2.connectedComponentsWithStats(matching.astype('uint8'))
            broad=any(area>small.shape[0]*small.shape[1]*.025 or (area>small.shape[0]*small.shape[1]*.002 and
                      (bw>small.shape[1]*.45 or bh>small.shape[0]*.70)
                      ) for left,top,bw,bh,area in stats[1:])
        precise=color_distance<2
        uniform=False
        if precise.sum()>small.shape[0]*small.shape[1]*.0015 and precise.sum()/max(1,raw_matching.sum())>.72:
            count,labels,raw_stats,_=cv2.connectedComponentsWithStats(raw_matching.astype('uint8'))
            uniform=any(bw>small.shape[1]*.18 or bh>small.shape[0]*.35 for left,top,bw,bh,area in raw_stats[1:] if area>small.shape[0]*small.shape[1]*.0005)
        # A photograph's sky or clothing can also be locally smooth. A panel
        # color needs support across the page or along more than one page edge.
        if broad or edge_support>=2 or uniform:
            colors.append(color)
    palette=np.asarray(colors, dtype='float32').reshape(-1, 3)
    if not len(palette):return palette
    # A skin/cloth patch inside a full-page photograph is not a page canvas.
    # Require flat panel colors along at least three substantial page edges.
    border=max(2,round(min(small.shape[:2])*.008))
    matching=_distance(small,palette)<10
    support=sum(float(part.mean())>.22 for part in
                (matching[:border],matching[-border:],matching[:,:border],matching[:,-border:]))
    if support<3:return np.empty((0,3),dtype='float32')
    return palette


def _distance(image, palette):
    import numpy as np
    distance = np.full(image.shape[:2], 999., dtype='float32')
    for color in palette:
        distance = np.minimum(distance, np.linalg.norm(image.astype('float32')-color, axis=2))
    return distance


def _text_mask(image, lines, scale, palette):
    import numpy as np
    mask = np.zeros(image.shape[:2], dtype='uint8')
    distance = _distance(image, palette)
    for line in lines:
        x0, y0, x1, y1 = [round(v*scale) for v in line['bbox']]
        x0, y0 = max(0, x0-2), max(0, y0-2)
        x1, y1 = min(mask.shape[1], x1+2), min(mask.shape[0], y1+2)
        region = distance[y0:y1, x0:x1]
        # Text on a picture is part of that picture. Only suppress lettering
        # whose enclosing area predominantly matches an inferred flat panel.
        if region.size and float((region < 18).mean()) > .54:
            mask[y0:y1, x0:x1] = 255
    return mask


def _coverage(a, b):
    x0, y0, x1, y1 = a
    xx0, yy0, xx1, yy1 = b
    return max(0, min(x1, xx1)-max(x0, xx0))*max(0, min(y1, yy1)-max(y0, yy0))/max(1, (x1-x0)*(y1-y0))


def _entropy(crop):
    import cv2
    import numpy as np
    gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
    hist=np.bincount((gray.ravel()//8),minlength=32).astype(float)
    p=hist[hist>0]/max(1,hist.sum())
    return float(-(p*np.log2(p)).sum())


def _panel_rows(image, bbox, palette):
    """Infer the hidden panel per row, retaining a horizontal panel boundary."""
    import numpy as np
    x0, y0, x1, y1 = bbox
    h, w = image.shape[:2]
    span = max(4, min(24, round(min(w, h)/90)))
    rows, reliable = [], []
    above=image[max(0,y0-span):max(1,y0-1),x0:x1].reshape(-1,3)
    below=image[min(h-1,y1+1):min(h,y1+span),x0:x1].reshape(-1,3)
    hints=[]
    for sample in (above,below):
        ds=np.linalg.norm(sample[:,None,:].astype(float)-palette[None,:,:],axis=2)
        ids=ds.argmin(axis=1); good=ds.min(axis=1)<18
        hints.append(palette[np.bincount(ids[good],minlength=len(palette)).argmax()] if good.any() else palette[0])
    for y in range(y0, y1):
        strips = []
        if x0:
            strips.append(image[y, max(0, x0-span):max(1, x0-1)])
        if x1 < w:
            strips.append(image[y, min(w-1, x1+1):min(w, x1+span)])
        samples = np.concatenate(strips, axis=0) if strips else np.empty((0, 3))
        if len(samples):
            distances = np.linalg.norm(samples[:, None, :].astype(float)-palette[None, :, :], axis=2)
            nearest = distances.argmin(axis=1)
            valid = distances.min(axis=1) < 18
            if valid.any():
                counts = np.bincount(nearest[valid], minlength=len(palette))
                best=counts.max()
                choices=np.flatnonzero(counts>=best*.68)
                # A photo can touch the boundary between two panels. In a tie,
                # consult the panel visible above or below rather than blindly
                # extending the first (usually pale) palette color across it.
                hint=hints[0]
                selected=choices[np.argmin(np.linalg.norm(palette[choices]-hint,axis=1))]
                color = palette[selected]
                confidence = float(valid.mean())
            else:
                color, confidence = palette[0], 0.
        else:
            color, confidence = palette[0], 0.
        rows.append(color)
        reliable.append(confidence)
    rows = np.asarray(rows, dtype='uint8')
    trusted = np.asarray(reliable) > .35
    if trusted.any():
        ids = np.flatnonzero(trusted)
        for i in np.flatnonzero(~trusted):
            rows[i] = rows[ids[np.argmin(abs(ids-i))]]
    return rows, float(trusted.mean())


def _panel_fill(image, bbox, palette, rows):
    """Extend visible vertical panel divisions through an extracted picture."""
    import numpy as np
    x0,y0,x1,y1=bbox
    h,w=image.shape[:2]
    fill=np.broadcast_to(rows[:,None,:],(y1-y0,x1-x0,3)).copy()
    band=max(3,min(15,round(min(h,w)/140)))
    top=image[max(0,y0-band):max(1,y0-1),x0:x1].astype(float)
    if not top.size:return fill
    profile=np.median(top,axis=0)
    distances=np.linalg.norm(profile[:,None,:]-palette[None,:,:],axis=2)
    labels=distances.argmin(axis=1)
    trusted=distances.min(axis=1)<18
    if trusted.mean()<.75:return fill
    indexes=np.flatnonzero(trusted)
    for i in np.flatnonzero(~trusted):labels[i]=labels[indexes[np.argmin(abs(indexes-i))]]
    for n,y in enumerate(range(y0,y1)):
        if not x0 or x1>=w:continue
        left=np.median(image[y,max(0,x0-band):max(1,x0-1)],axis=0)
        right=np.median(image[y,min(w-1,x1+1):min(w,x1+band)],axis=0)
        ld=np.linalg.norm(palette-left,axis=1);rd=np.linalg.norm(palette-right,axis=1)
        l,r=ld.argmin(),rd.argmin()
        if l==r or min(ld)>18 or min(rd)>18:continue
        # Only propagate a division that is present above the image, with the
        # same panel color on each end. Otherwise the row-wise fill is safer.
        if labels[0]==l and labels[-1]==r and (labels==l).mean()>.05 and (labels==r).mean()>.05:
            fill[n]=palette[labels]
    return fill


def _ellipse_panel(image,bbox,palette,rows):
    """Read a circle's immediate outer rim, rather than its rectangle corners."""
    import numpy as np
    x0,y0,x1,y1=bbox
    height,width=image.shape[:2]
    cx,cy=(x0+x1-1)/2,(y0+y1-1)/2
    rx,ry=(x1-x0)/2,(y1-y0)/2
    colors=rows.copy()
    band=max(4,min(18,round(min(height,width)/120)))
    for n,y in enumerate(range(y0,y1)):
        half=rx*math.sqrt(max(0,1-((y-cy)/max(1,ry))**2))
        left,right=round(cx-half),round(cx+half)
        strips=[image[y,max(0,left-band):max(0,left-2)],image[y,min(width,right+3):min(width,right+band)]]
        sample=np.concatenate(strips,axis=0)
        if not len(sample):continue
        distances=np.linalg.norm(sample[:,None,:].astype(float)-palette[None,:,:],axis=2)
        ids=distances.argmin(axis=1);valid=distances.min(axis=1)<18
        if valid.mean()>.35:
            colors[n]=palette[np.bincount(ids[valid],minlength=len(palette)).argmax()]
    return np.broadcast_to(colors[:,None,:],(y1-y0,x1-x0,3)).copy()


def _artwork(image, lines, palette):
    import cv2
    import numpy as np
    height, width = image.shape[:2]
    scale = min(1., 1600/max(width, height))
    size = (round(width*scale), round(height*scale))
    small = cv2.resize(image, size, interpolation=cv2.INTER_AREA)
    distance = _distance(small, palette)
    text = _text_mask(small, lines, scale, palette)
    mask = (distance > 24).astype('uint8')*255
    mask[text > 0] = 0
    # Closing joins illustration parts and texture holes without merging
    # pictures that are separated by a visible template gutter.
    kernel = max(3, round(min(size)/160)) | 1
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((kernel, kernel), 'uint8'))
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((3, 3), 'uint8'))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    objects = []
    minimum = max(14, min(size)/80)
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if min(bw, bh) < minimum or area < size[0]*size[1]*.00015:
            continue
        if bw*bh > size[0]*size[1]*.80:
            continue
        fill = area/(bw*bh)
        if fill < .13:
            continue
        crop = small[y:y+bh, x:x+bw]
        entropy=_entropy(crop)
        photo = ((fill>.66 and entropy>2.85) or (fill>.42 and entropy>3.25)) and min(bw, bh) > min(size)*.055
        # A large sparse component may be a connected decorative line spanning
        # the page. It is deliberately left in place rather than cut as a photo.
        if not photo:continue
        bbox = [max(0, math.floor(x/scale)), max(0, math.floor(y/scale)),
                min(width, math.ceil((x+bw)/scale)), min(height, math.ceil((y+bh)/scale))]
        # A connected card border must not turn a caption panel into a photo.
        # Two normal text lines on a flat panel make this candidate ambiguous;
        # retain that artwork in the background while keeping its text editable.
        protected=0
        first_text=height
        for line in lines:
            if len(line['text'])<5 or _coverage(line.get('glyph_bbox',line['bbox']),bbox)<.90:continue
            tx0,ty0,tx1,ty1=[round(v*scale) for v in line['bbox']]
            region=distance[max(0,ty0):min(size[1],ty1),max(0,tx0):min(size[0],tx1)]
            if region.size and float((region<18).mean())>.54:
                protected+=1
                first_text=min(first_text,ty0)
        if protected>=2:
            # A visible flat band between the photograph and its caption panel
            # is a trustworthy split. This also handles anti-aliased frames that
            # join those two regions in the foreground connected component.
            flat_rows=(distance[y:y+bh,x:x+bw]<6).mean(axis=1)>.68
            needed=max(3,round(bh*.008))
            split=None
            for row in range(max(1,round(bh*.20)),min(bh-needed,max(1,first_text-y))):
                if flat_rows[row:row+needed].all():split=row;break
            if split is None:continue
            new_bottom=min(height,math.floor((y+split)/scale))
            candidate=image[bbox[1]:new_bottom,bbox[0]:bbox[2]]
            if min(candidate.shape[:2])<minimum/scale or _entropy(candidate)<2.85:continue
            bbox[3]=new_bottom
        rows, confidence = _panel_rows(image, bbox, palette)
        if confidence < (.60 if photo else .72):
            continue
        objects.append({'bbox': bbox, 'kind': 'photo' if photo else 'illustration',
                        'fill': fill, 'rows': rows, 'confidence': confidence})
    # Closing can leave an isolated pocket inside a larger textured silhouette.
    # It is part of that artwork, never a second independently layered object.
    objects=[obj for obj in objects if not any(other is not obj and
             (_coverage(obj['bbox'],other['bbox'])>.94 or (_coverage(obj['bbox'],other['bbox'])>.15 and
              (other['bbox'][2]-other['bbox'][0])*(other['bbox'][3]-other['bbox'][1])>
              (obj['bbox'][2]-obj['bbox'][0])*(obj['bbox'][3]-obj['bbox'][1])*5)) and
             (other['bbox'][2]-other['bbox'][0])*(other['bbox'][3]-other['bbox'][1])>
             (obj['bbox'][2]-obj['bbox'][0])*(obj['bbox'][3]-obj['bbox'][1])*1.3 for other in objects)]
    return sorted(objects, key=lambda obj: (obj['bbox'][1], obj['bbox'][0]))


def _icons(image, lines, photos, palette):
    """Group clean silhouette edges, including artwork using another panel color."""
    import cv2
    import numpy as np
    height,width=image.shape[:2]
    scale=min(1.,1600/max(width,height))
    small=cv2.resize(image,(round(width*scale),round(height*scale)))
    edge=cv2.Canny(small,45,100)
    text=_text_mask(small,lines,scale,palette)
    edge[text>0]=0
    for obj in photos:
        x0,y0,x1,y1=[round(v*scale) for v in obj['bbox']]
        edge[max(0,y0-3):min(edge.shape[0],y1+3),max(0,x0-3):min(edge.shape[1],x1+3)]=0
    edge=cv2.dilate(edge,np.ones((3,3),'uint8'))
    edge=cv2.morphologyEx(edge,cv2.MORPH_CLOSE,np.ones((5,5),'uint8'))
    # Icons inside a colored panel are nested contours of that panel. RETR_LIST
    # keeps those interiors; the oversized panel contour is filtered below.
    contours,_=cv2.findContours(edge,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if min(bw,bh)<5 or max(bw,bh)<min(small.shape[:2])*.015:continue
        if bw>small.shape[1]*.30 or bh>small.shape[0]*.35:continue
        if cv2.contourArea(contour)<8:continue
        boxes.append([x,y,x+bw,y+bh])
    gap=max(5,min(small.shape[:2])/52)
    merged=True
    while merged:
        merged=False
        for i,a in enumerate(boxes):
            for j in range(i+1,len(boxes)):
                b=boxes[j]
                dx=max(0,a[0]-b[2],b[0]-a[2]);dy=max(0,a[1]-b[3],b[1]-a[3])
                union=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
                if dx<=gap and dy<=gap and union[2]-union[0]<small.shape[1]*.28 and union[3]-union[1]<small.shape[0]*.32:
                    boxes[i]=union;boxes.pop(j);merged=True;break
            if merged:break
    objects=[]
    for x0,y0,x1,y1 in boxes:
        bw,bh=x1-x0,y1-y0
        if min(bw,bh)<min(small.shape[:2])*.018:continue
        bbox=[max(0,math.floor(x0/scale)-1),max(0,math.floor(y0/scale)-1),
              min(width,math.ceil(x1/scale)+1),min(height,math.ceil(y1/scale)+1)]
        if bbox[0]<=1 or bbox[1]<=1 or bbox[2]>=width-1 or bbox[3]>=height-1:
            # A panel/ornament continuing off the page is not a bounded icon.
            continue
        if any(_coverage(bbox,obj['bbox'])>.2 for obj in photos):continue
        if any(len(line['text'])>3 and _coverage(line.get('glyph_bbox',line['bbox']),bbox)>.75 for line in lines):
            continue
        if .65<bw/max(1,bh)<1.50 and any(line['text'].isdigit() and _coverage(line.get('glyph_bbox',line['bbox']),bbox)>.85 for line in lines):continue
        crop=image[bbox[1]:bbox[3],bbox[0]:bbox[2]]
        if _entropy(crop)>3.15:continue
        rows,confidence=_panel_rows(image,bbox,palette)
        if confidence<.83:continue
        objects.append({'bbox':bbox,'kind':'illustration','rows':rows,'confidence':confidence})
    return sorted(objects,key=lambda obj:(obj['bbox'][1],obj['bbox'][0]))


def _elliptical_photos(image, lines, palette):
    """Separate a bounded photographic ellipse without cutting internal patches."""
    import cv2
    import numpy as np
    height,width=image.shape[:2]
    scale=min(1.,1400/max(width,height))
    small=cv2.resize(image,(round(width*scale),round(height*scale)))
    # Follow a closed outer boundary, including a circle inset in a colored
    # panel. Foreground palette masking alone would join it to that panel.
    edge=cv2.Canny(small,35,80)
    text=_text_mask(small,lines,scale,palette);edge[text>0]=0
    edge=cv2.morphologyEx(edge,cv2.MORPH_CLOSE,np.ones((3,3),'uint8'))
    contours,_=cv2.findContours(edge,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    result=[]
    for contour in contours:
        x,y,bw,bh=cv2.boundingRect(contour)
        if min(bw,bh)<min(small.shape[:2])*.12 or not .70<bw/max(1,bh)<1.40:continue
        ellipse_area=math.pi*bw*bh/4
        if abs(cv2.contourArea(contour)/max(1,ellipse_area)-1)>.09:continue
        points=contour[:,0,:].astype(float)
        radius=((points[:,0]-(x+(bw-1)/2))/max(1,bw/2))**2+((points[:,1]-(y+(bh-1)/2))/max(1,bh/2))**2
        if np.mean(abs(radius-1))>.06:continue
        bbox=[max(0,math.floor(x/scale)),max(0,math.floor(y/scale)),min(width,math.ceil((x+bw)/scale)),min(height,math.ceil((y+bh)/scale))]
        if _entropy(image[bbox[1]:bbox[3],bbox[0]:bbox[2]])<3:continue
        rows,confidence=_panel_rows(image,bbox,palette)
        if confidence<.80:continue
        result.append({'bbox':bbox,'kind':'photo','mask':'ellipse','rows':rows,'confidence':confidence})
    return result


def _shapes(image, lines, images, palette):
    """Recover only well-supported flat ellipses."""
    import cv2
    import numpy as np
    height, width = image.shape[:2]
    scale = min(1., 1400/max(width, height))
    small = cv2.resize(image, (round(width*scale), round(height*scale)))
    edge = cv2.Canny(small, 45, 100)
    for obj in images:
        x0, y0, x1, y1 = [round(v*scale) for v in obj['bbox']]
        edge[max(0,y0-2):min(edge.shape[0],y1+2),max(0,x0-2):min(edge.shape[1],x1+2)] = 0
    contours, _ = cv2.findContours(edge, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    shapes = []
    for contour in contours:
        if len(contour) < 12:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if min(bw, bh) < min(small.shape[:2])*.023 or max(bw,bh) > min(small.shape[:2])*.22:
            continue
        if not .72 < bw/max(1,bh) < 1.4:
            continue
        area = cv2.contourArea(contour)
        if abs(area/(math.pi*bw*bh/4)-1) > .07:
            continue
        bbox = [max(0,round(x/scale)),max(0,round(y/scale)),
                min(width,round((x+bw)/scale)),min(height,round((y+bh)/scale))]
        if any(_coverage(bbox,other['bbox'])>.45 for other in shapes):
            continue
        x0,y0,x1,y1=bbox
        crop=image[y0:y1,x0:x1]
        yy,xx=np.mgrid[:y1-y0,:x1-x0]
        inner=((xx-(x1-x0)/2)/max(1,(x1-x0)*.4))**2+((yy-(y1-y0)/2)/max(1,(y1-y0)*.4))**2<1
        values=crop[inner]
        if not len(values):continue
        color=np.median(values,axis=0)
        # The recognized number can live inside the circle; require most of
        # the inside to be one fill and an unlike, reliable exterior panel.
        if float((np.linalg.norm(values-color,axis=1)<18).mean())<.67:continue
        other_ink=inner&(np.linalg.norm(crop.astype(float)-color,axis=2)>18)
        recognized=np.zeros(inner.shape,dtype=bool)
        for line in lines:
            if _coverage(line.get('glyph_bbox',line['bbox']),bbox)<.85:continue
            ax0,ay0,ax1,ay1=line.get('glyph_bbox',line['bbox'])
            recognized[max(0,int(ay0)-y0-2):min(y1-y0,math.ceil(ay1)-y0+2),
                       max(0,int(ax0)-x0-2):min(x1-x0,math.ceil(ax1)-x0+2)]=True
        # Replacing a circle containing a pictogram with a solid ellipse would
        # erase that pictogram. Only recognized lettering may be reconstructed.
        if float((other_ink&~recognized).sum()/max(1,inner.sum()))>.015:continue
        rows,confidence=_panel_rows(image,bbox,palette)
        if confidence<.75 or np.linalg.norm(color-np.median(rows,axis=0))<35:continue
        shapes.append({'type':'ellipse','bbox':bbox,'color':[int(v) for v in color[::-1]],
                       'fill':[int(v) for v in color[::-1]],'rows':rows,'name':'识别圆形'})
    return shapes


def separate_artwork(image, lines, background_path, output_dir):
    """Return independent original picture crops and restore their hidden panel.

    OCR words inside photos stay raster, preserving book covers and captions.
    Ambiguous artwork on textured backgrounds remains in the background.
    """
    import cv2
    import numpy as np
    from PIL import Image
    palette=_palette(image)
    if not len(palette):
        if all(len(line['text'])<4 and line.get('confidence',0)<.97 for line in lines):
            # Short, uncertain OCR guesses on an ordinary full-page photograph
            # must not replace its pixels with false words or isolated strokes.
            ok,data=cv2.imencode('.png',image)
            if ok:data.tofile(str(background_path))
            return [],[],[]
        return lines,[],[]
    objects=_artwork(image,lines,palette)
    elliptical=_elliptical_photos(image,lines,palette)
    objects=[obj for obj in objects if not any(_coverage(obj['bbox'],oval['bbox'])>.80 for oval in elliptical)]
    objects+=elliptical
    objects+=_icons(image,lines,objects,palette)
    shapes=_shapes(image,lines,objects,palette)
    cleaned=cv2.imdecode(np.fromfile(str(background_path),dtype='uint8'),cv2.IMREAD_COLOR)
    if cleaned is None:raise ValueError('无法读取分层背景。')
    output_dir=Path(output_dir)
    images=[]
    for n,obj in enumerate(objects,1):
        x0,y0,x1,y1=obj['bbox']
        crop=image[y0:y1,x0:x1].copy()
        rows=obj['rows']
        panel=(_ellipse_panel(image,obj['bbox'],palette,rows) if obj.get('mask')=='ellipse'
               else _panel_fill(image,obj['bbox'],palette,rows))
        if obj.get('mask')=='ellipse':
            yy,xx=np.mgrid[:y1-y0,:x1-x0]
            rr=np.sqrt(((xx-(x1-x0-1)/2)/max(1,(x1-x0)/2))**2+((yy-(y1-y0-1)/2)/max(1,(y1-y0)/2))**2)
            alpha=np.clip((1-rr)*min(x1-x0,y1-y0)/2+.5,0,1)*255
            cleaned[y0:y1,x0:x1][alpha>0]=panel[alpha>0]
            asset=Image.fromarray(np.dstack((crop[:,:,::-1],alpha.astype('uint8'))))
        elif obj['kind']=='photo':
            # Full rectangle removal is essential: moving the photo must expose
            # its panel, not a duplicate baked into the slide background.
            cleaned[y0:y1,x0:x1]=panel
            asset=Image.fromarray(crop[:,:,::-1])
        else:
            delta=np.linalg.norm(crop.astype(float)-panel,axis=2)
            alpha=np.clip((delta-7)/12,0,1)*255
            alpha=cv2.morphologyEx(alpha.astype('uint8'),cv2.MORPH_CLOSE,np.ones((3,3),'uint8'))
            # Do not punch text holes or retain a rectangular patch around an icon.
            cleaned[y0:y1,x0:x1][alpha>0]=panel[alpha>0]
            asset=Image.fromarray(np.dstack((crop[:,:,::-1],alpha)))
        path=output_dir/(Path(background_path).stem+f'-image-{n}.png')
        asset.save(path)
        images.append({'path':str(path),'bbox':obj['bbox'],
                       'name':'独立照片' if obj['kind']=='photo' else '独立图标或插画'})
    filtered=[line for line in lines if not any(
              _coverage(line.get('glyph_bbox',line['bbox']),obj['bbox'])>.90 for obj in objects)]
    for shape in shapes:
        x0,y0,x1,y1=shape['bbox']
        yy,xx=np.mgrid[:y1-y0,:x1-x0]
        ellipse=((xx-(x1-x0-1)/2)/max(1,(x1-x0)/2))**2+((yy-(y1-y0-1)/2)/max(1,(y1-y0)/2))**2<=1.035
        area=cleaned[y0:y1,x0:x1]
        area[ellipse]=np.broadcast_to(shape.pop('rows')[:,None,:],area.shape)[ellipse]
    ok,data=cv2.imencode('.png',cleaned)
    if not ok:raise ValueError('无法保存分层背景。')
    data.tofile(str(background_path))
    return filtered,images,shapes
