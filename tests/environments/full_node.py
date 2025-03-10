from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Tuple, cast

from hddcoin.full_node.full_node import FullNode
from hddcoin.rpc.rpc_server import RpcServer
from hddcoin.server.server import HDDcoinServer
from hddcoin.server.start_service import Service
from hddcoin.simulator.full_node_simulator import FullNodeSimulator
from hddcoin.simulator.simulator_full_node_rpc_api import SimulatorFullNodeRpcApi
from tests.environments.common import ServiceEnvironment


@dataclass
class FullNodeEnvironment:
    if TYPE_CHECKING:
        _protocol_check: ClassVar[ServiceEnvironment[FullNode, SimulatorFullNodeRpcApi, FullNodeSimulator]] = cast(
            "FullNodeEnvironment",
            None,
        )

    __match_args__: ClassVar[Tuple[str, ...]] = ()

    service: Service[FullNode, FullNodeSimulator, SimulatorFullNodeRpcApi]

    @property
    def node(self) -> FullNode:
        return self.service._node

    @property
    def rpc_api(self) -> SimulatorFullNodeRpcApi:
        assert self.service.rpc_server is not None
        return self.service.rpc_server.rpc_api

    @property
    def rpc_server(self) -> RpcServer[SimulatorFullNodeRpcApi]:
        assert self.service.rpc_server is not None
        return self.service.rpc_server

    @property
    def peer_api(self) -> FullNodeSimulator:
        return self.service._api

    @property
    def peer_server(self) -> HDDcoinServer:
        return self.service._server
