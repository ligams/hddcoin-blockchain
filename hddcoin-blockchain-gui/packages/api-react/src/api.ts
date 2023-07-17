import { createApi } from '@reduxjs/toolkit/query/react';

import baseQuery from './hddcoinLazyBaseQuery';

export { baseQuery };

export default createApi({
  reducerPath: 'hddcoinApi',
  baseQuery,
  endpoints: () => ({}),
});
