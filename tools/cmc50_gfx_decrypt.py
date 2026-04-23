#!/usr/bin/env python3
"""CMC50 Neo Geo GFX (C ROM) decryption — from MAME's prot_cmc.cpp"""
import json, sys, time

def load_tables(table_file):
    return json.load(open(table_file))

def decrypt_gfx(rom, rom_size, tables, extra_xor=0):
    t03_0=tables['kof2000_type0_t03'];t12_0=tables['kof2000_type0_t12']
    t03_1=tables['kof2000_type1_t03'];t12_1=tables['kof2000_type1_t12']
    a815x1=tables['kof2000_address_8_15_xor1'];a815x2=tables['kof2000_address_8_15_xor2']
    a1623x1=tables['kof2000_address_16_23_xor1'];a1623x2=tables['kof2000_address_16_23_xor2']
    a07x=tables['kof2000_address_0_7_xor']
    
    nlong=rom_size//4
    buf=bytearray(rom_size)
    
    for rpos in range(nlong):
        off=4*rpos
        inv03=(rpos>>8)&1
        tmp=t03_1[(rpos&0xff)^a07x[(rpos>>8)&0xff]]
        xor0=(t03_0[(rpos>>8)&0xff]&0xfe)|(tmp&0x01)
        xor1=(tmp&0xfe)|(t12_0[(rpos>>8)&0xff]&0x01)
        if inv03:buf[off]=rom[off+3]^xor0;buf[off+3]=rom[off]^xor1
        else:buf[off]=rom[off]^xor0;buf[off+3]=rom[off+3]^xor1
        inv12=((rpos>>16)^a1623x2[(rpos>>8)&0xff])&1
        tmp=t12_1[(rpos&0xff)^a07x[(rpos>>8)&0xff]]
        xor0=(t12_0[(rpos>>8)&0xff]&0xfe)|(tmp&0x01)
        xor1=(tmp&0xfe)|(t03_0[(rpos>>8)&0xff]&0x01)
        if inv12:buf[off+1]=rom[off+2]^xor0;buf[off+2]=rom[off+1]^xor1
        else:buf[off+1]=rom[off+1]^xor0;buf[off+2]=rom[off+2]^xor1
    
    result=bytearray(rom_size)
    for rpos in range(nlong):
        baser=rpos^extra_xor
        baser^=a815x1[(baser>>16)&0xff]<<8
        baser^=a815x2[baser&0xff]<<8
        baser^=a1623x1[baser&0xff]<<16
        baser^=a1623x2[(baser>>8)&0xff]<<16
        baser^=a07x[(baser>>8)&0xff]
        baser&=(rom_size//4)-1
        result[4*rpos:4*rpos+4]=buf[4*baser:4*baser+4]
    
    return result

if __name__=='__main__':
    print("CMC50 GFX Decryption Tool")
    print("Tables: /tmp/kof2000_xor_tables.json")
    print("Usage: import and call decrypt_gfx(interleaved_rom, size, tables, extra_xor)")
