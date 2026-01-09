# TiMini Print Bluetooth Printer Tool

Alternative firmware/software replacing the “[Tiny Print](https://play.google.com/store/apps/details?id=com.frogtosea.tinyPrint)” Bluetooth thermal printers app.
Enables printing images, PDFs, or plain text directly from a desktop computer.
Supports GUI mode and a CLI "fire-and-forget" mode. Supports all [Bluetooth printer models](#supported-printer-models).

![TiMini Print LOGO EMX-040256 Printer Psi Patrol](EMX_040256.jpg)

##We need you!
- This is open source. Your small monthly support on [Buy Me a Coffee](https://buymeacoffee.com/dejniel) can make a real difference and keep the project alive—even a one-time donation helps. Building and maintaining a project like this takes a lot of time; if you find it useful, please consider supporting it so I can keep improving it: [support the project](https://buymeacoffee.com/dejniel).
- If you’re a developer, contributions and bug reports are always welcome—please jump in.

## Requirements
- Python 3.8+
- pip install -r requirements.txt
- Pair the printer in your OS Bluetooth settings and accept the trust/pairing
  prompt if shown. The app expects the device to be paired already.

## Quick start (GUI)
- Run with no arguments:
  python3 timiniprint.py

## Quick start (CLI)
- Print to the first supported Bluetooth printer:
  python3 timiniprint.py /path/to/file.pdf

- Print to a specific Bluetooth printer:
  python3 timiniprint.py --bluetooth "PRINTER_NAME" /path/to/file.pdf

- Print via a serial port (skip Bluetooth connection):
  python3 timiniprint.py --serial /dev/rfcomm0 /path/to/file.pdf

- List available printer models:
  python3 timiniprint.py --list-models

- Scan for supported printers:
  python3 timiniprint.py --scan

## Supported formats
- Images: .png .jpg .jpeg .gif .bmp
- PDF: prints all pages
- Text: .txt (monospace, bold if available)

## Notes
- Any CLI option/argument disables the GUI (no arguments = GUI mode).
- If `--bluetooth` is omitted, the first supported printer found is used.
- For `--serial`, you can pass `--bluetooth` to select the model explicitly.
- If no arguments are provided, a GUI opens. You can scan, connect/disconnect,
  choose a file, and print.

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
CTP750BY, TCM690464, U1, UXPORTMIP, WL01, X103H, X103h, X16, XC9, YK06, ZHHC, ZP801, ZP802, ZPA4Z1,
0019B-C, 0019B-D, 15P3, 58P5, AI01, AN01, DY01, Ewtto ET-Z0504, FL01, GB01, GB02, GB03, GB04, GB05,
GB06, GT01, GT02, GT03, GT04, GT08, JX001 JX01, JXM800 GG-D2100, LP100 LY10, LT01, LY01, LY02, LY03,
LY05, LY10, LY11, M01, M2, P1, P10, P5AI, P7, PR02, PR07, PR30, PR35, PR88, PR89, PR893, RT034h,
S01, S101, S102, XiaoWa, SC03, SC03h, SC04, SC04h, SC05, wts07, X1, X100, X101H, X102, X2H, X2h, X5,
X5H, X5HP, X5h, X6, X6H, X6HP, X6h, X7, X7H, X7HP, X7h, X8, X8-L, X8-W, X9, XW001 PR20, XW002 PR30,
XW003 PR25
