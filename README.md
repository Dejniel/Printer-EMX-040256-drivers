EMX-040256 Printer Tool (Linux, /dev/rfcomm0)

This is a small Python project for printing images and text to the EMX-040256
thermal printer over a serial Bluetooth SPP device (for example: /dev/rfcomm0).
The protocol and defaults are based on the Android app in this repo.

Requirements
- Python 3.8+
- pip install -r requirements.txt

Quick start
- Print an image:
  python3 print_emx_040256.py --image /path/to/photo.png
- Print text:
  python3 print_emx_040256.py --text "Hello EMX-040256"
- Use a custom device path:
  python3 print_emx_040256.py --device /dev/rfcomm0 --image /path/to/photo.png

Defaults (from EMX-040256 settings in the Android app)
- Width: 384 px
- Image speed: 10
- Text speed: 10
- Image energy: 5000
- Text energy: 8000
- Chunk size (MTU): 180 bytes
- Interval between chunks: 4 ms

Useful options
- --width: Override print width in pixels (must be divisible by 8).
- --image-energy / --text-energy: Override energy values.
- --speed: Override print speed.
- --blackening: 1..5 (print density level).
- --no-compress: Disable line RLE compression.
- --no-dither: Disable dithering for images.
- --font / --font-size: Text rendering options.
- --flow-control: Listen for flow control packets (if printer replies).

Notes
- The tool sends the same command structure used by the Android app for
  non-new-format devices. The printer may be one-way, so flow control is
  optional and disabled by default.
- If you have trouble with missing output, try increasing --interval-ms or
  lowering --chunk-size.
