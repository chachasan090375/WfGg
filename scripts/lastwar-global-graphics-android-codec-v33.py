#!/usr/bin/env python3
from __future__ import annotations

import math, re


def texture_format_name(tex) -> str:
    fmt=getattr(tex,'m_TextureFormat',None)
    name=getattr(fmt,'name',None)
    if name: return str(name)
    try:
        from UnityPy.enums import TextureFormat
        return TextureFormat(int(fmt)).name
    except Exception:
        return str(fmt or 'UNKNOWN')


def decode_texture2d(tex):
    """Android-safe Texture2D -> PIL.Image without Texture2D.image.

    This bypasses UnityPy's platform-sensitive high-level image path and decodes
    the exact Texture2D payload with texture2ddecoder.
    """
    from PIL import Image
    import texture2ddecoder as t2d

    w=int(getattr(tex,'m_Width',0) or 0); h=int(getattr(tex,'m_Height',0) or 0)
    if w<=0 or h<=0: raise ValueError('Texture2D dimensions invalides')
    raw=bytes(tex.get_image_data())
    if not raw: raise ValueError('Texture2D sans payload image')
    fmt=texture_format_name(tex); f=fmt.upper()

    # Mobile block compression. texture2ddecoder returns BGRA bytes.
    if f.startswith('ASTC_'):
        m=re.search(r'_(\d+)X(\d+)$',f)
        if not m: raise ValueError('Bloc ASTC inconnu: '+fmt)
        bw,bh=map(int,m.groups()); dec=t2d.decode_astc(raw,w,h,bw,bh)
        img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f in {'ETC_RGB4','ETC_RGB4_3DS'}:
        dec=t2d.decode_etc1(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='ETC2_RGB':
        dec=t2d.decode_etc2(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='ETC2_RGBA1':
        dec=t2d.decode_etc2a1(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='ETC2_RGBA8':
        dec=t2d.decode_etc2a8(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f in {'DXT1','BC1'}:
        dec=t2d.decode_bc1(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f in {'DXT5','BC3'}:
        dec=t2d.decode_bc3(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='BC4':
        dec=t2d.decode_bc4(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='BC5':
        dec=t2d.decode_bc5(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f in {'BC6H','BC6'}:
        dec=t2d.decode_bc6(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='BC7':
        dec=t2d.decode_bc7(raw,w,h); img=Image.frombytes('RGBA',(w,h),dec,'raw','BGRA')
    elif f=='RGBA32':
        img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','RGBA')
    elif f=='BGRA32':
        img=Image.frombytes('RGBA',(w,h),raw[:w*h*4],'raw','BGRA')
    elif f=='ARGB32':
        # Unity bytes are A,R,G,B. Convert explicitly to RGBA rather than relying
        # on a Pillow raw mode that is not present on every Android build.
        buf=bytearray(w*h*4)
        for i in range(0,min(len(raw),w*h*4),4):
            a,r,g,b=raw[i:i+4]; buf[i:i+4]=bytes((r,g,b,a))
        img=Image.frombytes('RGBA',(w,h),bytes(buf),'raw','RGBA')
    elif f=='RGB24':
        img=Image.frombytes('RGB',(w,h),raw[:w*h*3],'raw','RGB').convert('RGBA')
    elif f=='ALPHA8':
        a=Image.frombytes('L',(w,h),raw[:w*h]); img=Image.new('RGBA',(w,h),(255,255,255,0)); img.putalpha(a)
    elif f=='R8':
        r=Image.frombytes('L',(w,h),raw[:w*h]); img=Image.merge('RGBA',(r,r,r,Image.new('L',(w,h),255)))
    else:
        raise ValueError('Format Texture2D non pris en charge par le codec Android V33: '+fmt)

    return img.transpose(Image.Transpose.FLIP_TOP_BOTTOM),fmt


def export_mesh_obj(mesh) -> str:
    """Manual MeshHandler -> OBJ, independent of UnityPy's high-level exporter."""
    from UnityPy.helpers.MeshHelper import MeshHandler
    h=MeshHandler(mesh); h.process()
    if h.m_VertexCount<=0 or not h.m_Vertices:
        raise ValueError('Mesh sans sommets décodables')
    name=str(getattr(mesh,'m_Name','') or 'mesh')
    out=[f'g {name}\n']
    for p in h.m_Vertices:
        vals=[0.0 if not math.isfinite(float(v)) else float(v) for v in p[:3]]
        out.append('v {:.9g} {:.9g} {:.9g}\n'.format(-vals[0],vals[1],vals[2]))
    has_uv=bool(h.m_UV0); has_n=bool(h.m_Normals)
    if has_uv:
        for uv in h.m_UV0:
            u=0.0 if not math.isfinite(float(uv[0])) else float(uv[0]); v=0.0 if not math.isfinite(float(uv[1])) else float(uv[1])
            out.append('vt {:.9g} {:.9g}\n'.format(u,v))
    if has_n:
        for n in h.m_Normals:
            vals=[0.0 if not math.isfinite(float(v)) else float(v) for v in n[:3]]
            out.append('vn {:.9g} {:.9g} {:.9g}\n'.format(-vals[0],vals[1],vals[2]))
    for si,tris in enumerate(h.get_triangles()):
        out.append(f'g {name}_{si}\n')
        for a,b,c in tris:
            a,b,c=int(a)+1,int(b)+1,int(c)+1
            if has_uv and has_n: out.append(f'f {c}/{c}/{c} {b}/{b}/{b} {a}/{a}/{a}\n')
            elif has_uv: out.append(f'f {c}/{c} {b}/{b} {a}/{a}\n')
            elif has_n: out.append(f'f {c}//{c} {b}//{b} {a}//{a}\n')
            else: out.append(f'f {c} {b} {a}\n')
    return ''.join(out)
