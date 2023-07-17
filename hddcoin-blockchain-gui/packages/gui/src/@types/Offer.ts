import { type OfferSummaryRecord } from '@hddcoin-network/api';

type Offer = {
  id: string;
  valid: boolean;
  data: string;
  summary: OfferSummaryRecord;
};

export default Offer;
