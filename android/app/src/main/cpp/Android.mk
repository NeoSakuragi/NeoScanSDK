# One library: the Geolith core (its own source list, libretro/Makefile.common) + the JNI front end player.c.
LOCAL_PATH := $(call my-dir)
GEOLITH := $(abspath $(LOCAL_PATH)/../../../../../geolith)
CORE_DIR := $(GEOLITH)
include $(GEOLITH)/libretro/Makefile.common

include $(CLEAR_VARS)
LOCAL_MODULE    := neoplayer
PACKSWAP := $(abspath $(LOCAL_PATH)/../../../../../tools/brawler/chainlab)
LOCAL_SRC_FILES := $(SOURCES_C) $(LOCAL_PATH)/player.c $(PACKSWAP)/pack_swap.c
LOCAL_C_INCLUDES := $(GEOLITH)/libretro $(PACKSWAP)
LOCAL_CFLAGS    := -DANDROID -D__LIBRETRO__ -DZ7_ST -O2 $(INCFLAGS) $(FLAGS)
LOCAL_LDLIBS    := -lz -llog
include $(BUILD_SHARED_LIBRARY)
