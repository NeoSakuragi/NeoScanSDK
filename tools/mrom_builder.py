#!/usr/bin/env python3
"""Generate Neo Geo Z80 M ROM — SDCC sequence player."""
import argparse, os, struct, subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SDK_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'sdk')
SOUND_DIR = os.path.join(SDK_DIR, 'sound')

MROM_SIZE = 0x20000
SFX_TABLE = 0x0800
FM_FREQ   = 0x0A00
SEQ_HDR   = 0x0C00

def build_driver():
    crt0 = os.path.join(SOUND_DIR, 'crt0_z80.s')
    src = os.path.join(SOUND_DIR, 'driver.c')
    subprocess.check_call(['sdasz80','-o',
        os.path.join(SOUND_DIR,'crt0_z80.rel'), crt0], cwd=SOUND_DIR)
    subprocess.check_call(['sdcc','-mz80','--no-std-crt0','-c',
        src,'-o',os.path.join(SOUND_DIR,'driver.rel')], cwd=SOUND_DIR)
    subprocess.check_call(['sdcc','-mz80','--no-std-crt0',
        '--code-loc','0x00A0','--data-loc','0xF800',
        '-o',os.path.join(SOUND_DIR,'driver.ihx'),
        os.path.join(SOUND_DIR,'crt0_z80.rel'),
        os.path.join(SOUND_DIR,'driver.rel')], cwd=SOUND_DIR)
    subprocess.check_call(['sdobjcopy','-Iihex','-Obinary',
        os.path.join(SOUND_DIR,'driver.ihx'),
        os.path.join(SOUND_DIR,'driver.bin')], cwd=SOUND_DIR)
    return open(os.path.join(SOUND_DIR,'driver.bin'),'rb').read()

def build_mrom(sample_table_bin=None, music_bins=None, voice_table_bin=None,
               seq_blob=None, fm_freq_table=None):
    driver = build_driver()
    mrom = bytearray(MROM_SIZE)
    mrom[:len(driver)] = driver
    if sample_table_bin:
        mrom[SFX_TABLE:SFX_TABLE+len(sample_table_bin)] = sample_table_bin
    if fm_freq_table:
        mrom[FM_FREQ:FM_FREQ+len(fm_freq_table)] = fm_freq_table
    if seq_blob:
        end = SEQ_HDR + len(seq_blob)
        if end > 0xC000:
            print(f"  WARNING: seq data ends at ${end:04X}, past $BFFF!")
        mrom[SEQ_HDR:SEQ_HDR+len(seq_blob)] = seq_blob
        print(f"  Seq data: {len(seq_blob):,} bytes at ${SEQ_HDR:04X}-${end-1:04X}")
    elif music_bins and len(music_bins) > 0:
        first = music_bins[0]
        ni, ns, np = first[0], first[1], first[2]
        meta = 4 + ni*30 + ns*4 + np*7
        nt = len(music_bins)
        patched = bytearray(first[:meta])
        patched[3] = nt
        track_table_size = nt * 4
        streams_start = meta + track_table_size
        track_table = bytearray()
        all_streams = bytearray()
        for i, mb in enumerate(music_bins):
            stream = mb[meta:]
            stream_off = streams_start + len(all_streams)
            track_table += struct.pack('<HH', stream_off, 0xFFFF)
            all_streams += stream
            print(f"  Track {i}: {len(stream):,} bytes at offset 0x{stream_off:04X}")
        patched += track_table
        patched += all_streams
        mrom[SEQ_HDR:SEQ_HDR+len(patched)] = patched
        print(f"  Music: {nt} tracks, {len(all_streams):,} bytes total")
    return bytes(mrom)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-o','--output',required=True)
    parser.add_argument('--sample-table',default=None)
    parser.add_argument('--voice-table',default=None)
    parser.add_argument('--music',action='append',default=[])
    parser.add_argument('--seq-blob',default=None)
    parser.add_argument('--fm-freq-table',default=None)
    args = parser.parse_args()
    t = open(args.sample_table,'rb').read() if args.sample_table and os.path.exists(args.sample_table) else None
    v = open(args.voice_table,'rb').read() if args.voice_table and os.path.exists(args.voice_table) else None
    s = open(args.seq_blob,'rb').read() if args.seq_blob and os.path.exists(args.seq_blob) else None
    f = open(args.fm_freq_table,'rb').read() if args.fm_freq_table and os.path.exists(args.fm_freq_table) else None
    m = [open(p,'rb').read() for p in args.music if os.path.exists(p)]
    mrom = build_mrom(t, m if m else None, v, seq_blob=s, fm_freq_table=f)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)),exist_ok=True)
    open(args.output,'wb').write(mrom)
    print(f"M ROM: {args.output} ({len(mrom):,} bytes)")

if __name__=='__main__': main()
