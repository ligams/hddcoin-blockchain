# hddcoin-blockchain-gui/api

![HDDcoin logo](https://www.hddcoin.org/wp-content/uploads/2022/09/hddcoin-logo.svg)

![GitHub contributors](https://img.shields.io/github/contributors/HDDcoin-Network/hddcoin-blockchain-gui?logo=GitHub)

This library provides support for TypeScript/JavaScript [HDDcoin](https://www.hddcoin.org) apps to access the [HDDcoin Blockchain RPC](https://docs.hddcoin.org/rpc/), by making it easier to perform the following actions:

- Making requests to the HDDcoin Blockchain RPC.
- Catch responses and errors with standard try/catch and async/await syntax.
- Catch error when the request has a timeout. Each request has a default timeout of 10 minutes.
- Auto-connect to daemon when you send the first request.
- Auto-reconnect when the connection was disconnected.
- Transforming request/response and using standard [camel case](https://en.wikipedia.org/wiki/Camel_case) format for properties and responses. Internally will be everything converted to [snake case](https://en.wikipedia.org/wiki/Snake_case).
- Providing types for requests and responses.

## Example

```ts
import { readFileSync } from "fs";
import Client, { Wallet } from '@hddcoin-network/api'; // or from "../hddcoin-blockchain/hddcoin-blockchain-gui/packages/api";
import Websocket from 'ws';
import sleep from 'sleep-promise';

(async () => {
  const client = new Client({
    url: 'wss://127.0.0.1:25400',
    // key and crt files should be in your homedir in: .hddcoin/mainnet/config/ssl/daemon/
    cert: readFileSync('private_cert.crt'),
    key: readFileSync('private_key.key'),
    webSocket: Websocket;
  });

  const wallet = new Wallet(client);

  try {
    // get list of available public keys
    const publicKeys = await wallet.getPublicKeys();

    // bind to sync changes
    const unsubscribeSyncChanges = wallet.onSyncChanged((syncData) => {
      console.log('do something with synchronization data');
    });

    // wait 5 minutes
    await sleep(1000 * 60 * 5);

    // unsubscribe from synchronization changes
    await unsubscribeSyncChanges();

    // wait 5 minutes
    await sleep(1000 * 60 * 5);

    // close client and stop all services
    await client.close();
  } catch (error: any) {
    // something went wrong (timeout or error on the backend side)
    console.log(error.message);
  }
})();
```

## Development

Please read and follow the main [README.md](https://github.com/HDDcoin-Network/hddcoin-blockchain-gui) of this monorepo.
