---
# ============ front matter 字段说明 ============
title: "STM32 智能手表项目：从选型到固件框架"
date: 2026-09-25
tags: [embedded, stm32, rtos, display, arm]
summary: "记录一个基于 STM32 的智能手表项目模板：硬件选型、固件框架与驱动示例。"
# slug: "custom-url"          # 可选，默认取文件名
# draft: true                 # 设为 true 时不发布
# toc: false                  # 可选，单独关闭本文目录
# ===============================================
---

这是一个基于 STM32 的智能手表项目模板，用于演示 Markdown 写法、
文章目录（TOC）、代码高亮、表格与标签。

## 项目目标

- 低功耗常亮显示
- 蓝牙通知同步
- 按键与触摸交互
- 可充电锂电池供电

## 硬件选型

### 主控与存储

| 模块 | 型号 | 说明 |
| --- | --- | --- |
| MCU | STM32L4R9 | Cortex-M4，带 MIPI DSI 与 Chrom-ART |
| 屏幕 | 1.4" AMOLED | 466×466，SPI/QSPI 接口 |
| 存储 | MX25U6432F | 8MB QSPI NOR Flash |
| 电池 | 400mAh | 3.7V 锂聚合物电池 |

### 传感器与外设

主控、屏幕、传感器之间通过 SPI 与 I2C 互联，下面重点记录 SPI DMA 的调试过程。

## 固件框架

### 启动流程

```c
/* reset_handler：进入 C 环境前完成栈初始化 */
extern void Reset_Handler(void) __attribute__((noreturn));

void Reset_Handler(void) {
    __asm volatile(
        "ldr r0, =_estack\n"
        "mov sp, r0\n"
    );
    SystemInit();
    __libc_init_array();
    main();
    for (;;) { }
}
```

### 低功耗设计

```arm
.syntax unified
.thumb

sleep_now:
    cpsid i
    wfe
    b    sleep_now
```

## 构建与烧录

```bash
#!/bin/sh
set -eu

make -j"$(nproc)"
openocd -f interface/stlink.cfg \
        -f target/stm32l4x.cfg \
        -c "program build/watch.elf verify reset exit"
```

## 参考资料

- [STM32L4R9 参考手册](https://www.st.com/)
- [ARM Cortex-M4 技术参考手册](https://developer.arm.com/)
