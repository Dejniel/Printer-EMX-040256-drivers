# TiMini Print Bluetooth Printer Tool

Alternative desktop software for Chinese Bluetooth thermal printers that use proprietary protocols (not ESC/POS), replacing apps like “Tiny Print” or “iBleem”. These printers are often sold under generic names such as “thermal printer”, “POS printer”, “mini printer”, or “cat printer”.
It lets you print images, PDFs, or plain text from your computer.
Supports both a GUI and a “fire-and-forget” CLI mode. Check the list of [supported Bluetooth printer models](#supported-printer-models).

![TiMini Print LOGO EMX-040256 Printer Psi Patrol](EMX_040256.jpg)

## We need you!
- This project is open source! Your small monthly support on [Buy Me a Coffee](https://buymeacoffee.com/dejniel) can make a real difference and help keep it going—even a one-time donation helps. Building and maintaining a project like this takes a lot of time; if you find it useful, please consider supporting it so I can keep improving it: [support the project](https://buymeacoffee.com/dejniel)
- If you're a developer, contributions and bug reports are always welcome—please jump in. Especially if you use or build on non-Linux systems, please consider contributing fixes or improvements

## Requirements
- Python 3.8+
- pip install -r requirements.txt

## Quick start (GUI)
- If no arguments are provided, a GUI opens. You can scan, connect/disconnect,
  choose a file, and print. Run with no arguments:
  python3 timiniprint.py

## Quick start (CLI)
- Print to the first supported Bluetooth printer:
  python3 timiniprint.py /path/to/file.pdf

- Print to a specific Bluetooth printer:
  python3 timiniprint.py --bluetooth "PRINTER_NAME" /path/to/file.pdf

- Print via a serial port (skip Bluetooth connection):
  python3 timiniprint.py --serial /dev/rfcomm0 --model A200 /path/to/file.pdf

- Print raw text without creating a file:
  python3 timiniprint.py --text "Hello from CLI"

- List available printer models:
  python3 timiniprint.py --list-models

- Scan for supported printers:
  python3 timiniprint.py --scan

### Notes
- Any CLI option/argument disables the GUI (no arguments = GUI mode)
- If `--bluetooth` is omitted, the first supported printer found is used
- For `--serial`, you must pass `--model` (see `--list-models`)
- For Bluetooth printing, you can pass `--model` to override auto-detection
- `--force-text-mode` / `--force-image-mode` force the printer protocol mode

## Supported formats
- Images: .png .jpg .jpeg .gif .bmp
- PDF: prints all pages
- Text: .txt (monospace, bold if available)

## Notes
- I test builds only on Ubuntu-like systems—if you need to run this elsewhere, please report issues or submit a fix :P
- Windows + Python 3.13+: installing `winsdk` may require building binaries during download
- Protocol integration guide: [docs/protocol.md](docs/protocol.md)

## PDF rendering dependencies (optional)
- PyMuPDF: pip install pymupdf
- pdf2image: pip install pdf2image (plus system poppler)
- Or system pdftoppm (poppler-utils)

## Supported printer models
A200, A33, A41II, A41III, A42II, A43, A4300, CMT-0510, CP01, D1, D100, DL GE225, DL X2, DL X2 Pro,
DL X7, DL X7 Pro, DT1-0, DTR-R0, DY03, DY49, EMX-040256, FC02, GB02SH, GB03PH, GB03PL, GB03SH,
GB03SL, GL-VS9, GT09, GT10, GV-MA211, GW08, GW09, HD1, HT0125, IM.04, IprintIt Printer,
JRX01, KF-5, LGM01, LP6, Label Printer CPLM10, Luxorp.PX10, ML-MP-01, MPA81, MV-B530, Mini Printer
CTP500, P2, P4, P5, P6, P7H, PT001, Pocket Printer, Professional Printer CTP100LG, QDID, QDX01,
ROSSMANN, RS9000, SC03H, Seznik Echo, Seznik Neo, Shipping Printer CTP800BD, Shipping Printer
CTP750BY, TCM690464, U1, UXPORTMIP, WL01, X103H, X103h, X16, XC9, YK06, YT01, ZHHC, ZP801, ZP802, ZPA4Z1,
0019B-C, 0019B-D, 15P3, 58P5, AI01, AN01, DY01, Ewtto ET-Z0504, FL01, GB01, GB02, GB03, GB04, GB05,
GB06, GT01, GT02, GT03, GT04, GT08, JX001 JX01, JX002 JX02, JX003 JX03, JX004 JX04, JX005 JX05,
JX006 JX06, JXM800 GG-D2100, LP100 LY10, LT01, LY01, LY02, LY03,
LY05, LY10, LY11, M01, M2, MX05, MX06, MX08, MX09, MX10, MX11, P1, P10, P5AI, P7, PR02, PR07, PR30, PR35, PR88, PR89, PR893, RT034h,
S01, S101, S102, XiaoWa, SC03, SC03h, SC04, SC04h, SC05, wts07, X1, X100, X101H, X102, X2H, X2h, X5,
X5H, X5HP, X5h, X6, X6H, X6HP, X6h, X7, X7H, X7HP, X7h, X8, X8-L, X8-W, X9, XW001 PR20, XW002 PR30,
XW003 PR25, XW004 PR35, XW005 PR88, XW006 PR89, XW007 PR893, XW008 PR02, XW009 PR07
