import { createApi } from '@reduxjs/toolkit/query/react';

import hddcoinLazyBaseQuery from './hddcoinLazyBaseQuery';

export const baseQuery = hddcoinLazyBaseQuery({});

export default createApi({
  reducerPath: 'hddcoinApi',
  baseQuery,
  endpoints: () => ({}),
});
