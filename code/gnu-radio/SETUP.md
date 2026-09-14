# USEFUL COMMANDS
## ACTIVATE CONDA ENV
```bash
conda activate gr
    ```

## RUN GNU RADIO GUI

```bash
conda activate gr
gnuradio-companion
```

## RTL TEST COMMANDS (run test fm)
```bash
rtl_fm -f 92.3M -M wbfm - | play -r 32k -t raw -e signed -b 16 -c 1 -V1 -
```

```bash
python code/gnu-radio/iq_bridge.py --tune 1.17e6
```