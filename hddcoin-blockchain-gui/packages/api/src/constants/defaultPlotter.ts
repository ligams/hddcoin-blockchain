import defaultsForPlotter from '../utils/defaultsForPlotter';
import optionsForPlotter from '../utils/optionsForPlotter';
import PlotterName from './PlotterName';

export default {
  displayName: 'HDDcoin Proof of Space',
  options: optionsForPlotter(PlotterName.HDDCOINPOS),
  defaults: defaultsForPlotter(PlotterName.HDDCOINPOS),
  installInfo: { installed: true },
};
