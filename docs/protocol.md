# Protocol Integration Guide

The `timiniprint.protocol` package provides the raw encoder for Tiny Print compatible
printers. It builds the byte stream you need to send over your own transport
(Bluetooth SPP, serial, etc.). It does not handle device discovery or I/O.

## Quick start (manual settings)

```python
from timiniprint.protocol import Raster, build_job_from_raster

# Example: 8x8 black square.
width = 8
height = 8
raster = Raster(pixels=[1] * (width * height), width=width)  # 1 = black, 0 = white

data = build_job_from_raster(
    raster,
    is_text=False,
    speed=6,
    energy=5000,
    blackening=3,
    compress=True,
    lsb_first=True,
    new_format=False,
    feed_padding=12,
    dev_dpi=203,
)

# Send `data` using your own transport.
```

## From renderer to protocol

The renderer produces the `pixels` list used by the protocol. The `Raster` helper
is the expected intermediate format between rendering and encoding.

```python
from PIL import Image

from timiniprint.protocol import Raster, build_job_from_raster
from timiniprint.rendering.renderer import image_to_bw_pixels

img = Image.open("example.png")
target_width = img.width - (img.width % 8)
if target_width != img.width:
    target_height = max(1, int(img.height * target_width / img.width))
    img = img.resize((target_width, target_height), Image.LANCZOS)

pixels = image_to_bw_pixels(img, dither=True)
raster = Raster(pixels=pixels, width=img.width)

data = build_job_from_raster(
    raster,
    is_text=False,
    speed=6,
    energy=5000,
    blackening=3,
    compress=True,
    lsb_first=True,
    new_format=False,
    feed_padding=12,
    dev_dpi=203,
)
```

## Using printer models from this repo

The protocol values (speed, energy, new_format, etc.) are printer-specific. You can
reuse the model registry shipped with this project:

```python
from timiniprint.devices import PrinterModelRegistry
from timiniprint.protocol import Raster, build_job_from_raster

registry = PrinterModelRegistry.load()
model = registry.get("EMX-040256")
if not model:
    raise RuntimeError("Unknown model")

width = model.width - (model.width % 8)
raster = Raster(pixels=pixels, width=width)
data = build_job_from_raster(
    raster,
    is_text=False,
    speed=model.img_print_speed,
    energy=model.moderation_energy or 5000,
    blackening=3,
    compress=model.new_compress,
    lsb_first=not model.a4xii,
    new_format=model.new_format,
    feed_padding=12,
    dev_dpi=model.dev_dpi,
)
```

## Inputs and expectations

- `Raster`: helper object with `pixels` and `width` (row-major 0/1 buffer)
- `pixels`: flat list of 0/1 values (row-major), length = `width * height`
- `width`: must be divisible by 8 and match `pixels` length
- `lsb_first`: bit order for packed lines (varies by model)
- `new_format`: toggles the printer's newer header format
- `compress`: enables line RLE compression

## Related modules (optional)

- `timiniprint.printing` builds print jobs from files (images/PDF/text)
- `timiniprint.transport` provides Bluetooth/serial transports you can reuse
