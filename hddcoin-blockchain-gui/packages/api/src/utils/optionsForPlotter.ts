import { PlotterOptions } from '../@types/Plotter';
import PlotterName from '../constants/PlotterName';
import { bladebitRamOptions, bladebitDiskOptions, madmaxOptions, chiaposOptions } from '../constants/Plotters';

export default function optionsForPlotter(plotterName: PlotterName): PlotterOptions {
  switch (plotterName) {
    case PlotterName.BLADEBIT_RAM:
      return bladebitRamOptions;
    case PlotterName.BLADEBIT_DISK:
      return bladebitDiskOptions;
    case PlotterName.MADMAX:
      return madmaxOptions;
    case PlotterName.HDDCOINPOS: // fallthrough
    default:
      return chiaposOptions;
  }
}
