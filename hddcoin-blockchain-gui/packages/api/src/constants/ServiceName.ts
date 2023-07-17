const ServiceName = {
  WALLET: 'hddcoin_wallet',
  FULL_NODE: 'hddcoin_full_node',
  FARMER: 'hddcoin_farmer',
  HARVESTER: 'hddcoin_harvester',
  SIMULATOR: 'hddcoin_full_node_simulator',
  DAEMON: 'daemon',
  PLOTTER: 'hddcoin_plotter',
  TIMELORD: 'hddcoin_timelord',
  INTRODUCER: 'hddcoin_introducer',
  EVENTS: 'wallet_ui',
  DATALAYER: 'hddcoin_data_layer',
  DATALAYER_SERVER: 'hddcoin_data_layer_http',
} as const;

type ObjectValues<T> = T[keyof T];

export type ServiceNameValue = ObjectValues<typeof ServiceName>;

export default ServiceName;
