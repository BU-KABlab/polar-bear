# Hardware

The Polar Bear station combines a motion platform and liquid-handling hardware coordinated by CubOS with two Arduino Nano accessory modules:

1. A 24-pixel RGBW NeoPixel ring for controlled illumination.
2. A capper/decapper accessory using an IR break-beam sensor and a 5 V electromagnet driven through an IRLZ44N MOSFET and flyback diode.

The wiring diagram is in `electronics/circuit-diagram.png`. The matching embedded programs are under `firmware/`.

The diagram records the current build information from the source folder. Before reproducing the hardware, independently verify component ratings, power supply capacity, grounding, polarity, and the physical wiring against the actual station.
