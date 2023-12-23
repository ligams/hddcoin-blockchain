from __future__ import annotations

from hddcoin.data_layer.data_layer import DataLayer
from hddcoin.data_layer.data_layer_api import DataLayerAPI
from hddcoin.farmer.farmer import Farmer
from hddcoin.farmer.farmer_api import FarmerAPI
from hddcoin.full_node.full_node import FullNode
from hddcoin.full_node.full_node_api import FullNodeAPI
from hddcoin.harvester.harvester import Harvester
from hddcoin.harvester.harvester_api import HarvesterAPI
from hddcoin.introducer.introducer import Introducer
from hddcoin.introducer.introducer_api import IntroducerAPI
from hddcoin.rpc.crawler_rpc_api import CrawlerRpcApi
from hddcoin.rpc.data_layer_rpc_api import DataLayerRpcApi
from hddcoin.rpc.farmer_rpc_api import FarmerRpcApi
from hddcoin.rpc.full_node_rpc_api import FullNodeRpcApi
from hddcoin.rpc.harvester_rpc_api import HarvesterRpcApi
from hddcoin.rpc.timelord_rpc_api import TimelordRpcApi
from hddcoin.rpc.wallet_rpc_api import WalletRpcApi
from hddcoin.seeder.crawler import Crawler
from hddcoin.seeder.crawler_api import CrawlerAPI
from hddcoin.server.start_service import Service
from hddcoin.simulator.full_node_simulator import FullNodeSimulator
from hddcoin.simulator.simulator_full_node_rpc_api import SimulatorFullNodeRpcApi
from hddcoin.timelord.timelord import Timelord
from hddcoin.timelord.timelord_api import TimelordAPI
from hddcoin.wallet.wallet_node import WalletNode
from hddcoin.wallet.wallet_node_api import WalletNodeAPI

CrawlerService = Service[Crawler, CrawlerAPI, CrawlerRpcApi]
DataLayerService = Service[DataLayer, DataLayerAPI, DataLayerRpcApi]
FarmerService = Service[Farmer, FarmerAPI, FarmerRpcApi]
FullNodeService = Service[FullNode, FullNodeAPI, FullNodeRpcApi]
HarvesterService = Service[Harvester, HarvesterAPI, HarvesterRpcApi]
IntroducerService = Service[Introducer, IntroducerAPI, FullNodeRpcApi]
SimulatorFullNodeService = Service[FullNode, FullNodeSimulator, SimulatorFullNodeRpcApi]
TimelordService = Service[Timelord, TimelordAPI, TimelordRpcApi]
WalletService = Service[WalletNode, WalletNodeAPI, WalletRpcApi]
