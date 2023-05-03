import { Trans, Plural } from '@lingui/macro';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import { Box, IconButton, InputAdornment, FormControl, FormHelperText } from '@mui/material';
import BigNumber from 'bignumber.js';
import React, { type ReactNode } from 'react';
import { useWatch, useFormContext } from 'react-hook-form';

import useCurrencyCode from '../../hooks/useCurrencyCode';
import catToByte from '../../utils/catToByte';
import hddcoinToByte from '../../utils/hddcoinToByte';
import Flex from '../Flex';
import FormatLargeNumber from '../FormatLargeNumber';
import TextField, { TextFieldProps } from '../TextField';
import NumberFormatCustom from './NumberFormatCustom';

export type AmountProps = TextFieldProps & {
  children?: (props: { byte: BigNumber; value: string | undefined }) => ReactNode;
  name?: string;
  symbol?: string; // if set, overrides the currencyCode. empty string is allowed
  showAmountInBytes?: boolean; // if true, shows the byte amount below the input field
  dropdownAdornment?: func;
  label?: ReactNode;
  'data-testid'?: string;
};

export default function Amount(props: AmountProps) {
  const {
    children,
    name = 'amount',
    symbol,
    showAmountInBytes = true,
    dropdownAdornment,
    variant,
    fullWidth,
    'data-testid': dataTestid,
    label = <Trans>Amount</Trans>,
    ...rest
  } = props;
  const { control } = useFormContext();
  const defaultCurrencyCode = useCurrencyCode();

  const value = useWatch<string>({
    control,
    name,
  });

  const correctedValue = value && value[0] === '.' ? `0${value}` : value;

  const currencyCode = symbol === undefined ? defaultCurrencyCode : symbol;
  const isHDDcoinCurrency = ['HDD', 'THDD'].includes(currencyCode);
  const byte = isHDDcoinCurrency ? hddcoinToByte(correctedValue) : catToByte(correctedValue);

  return (
    <FormControl variant={variant} fullWidth={fullWidth}>
      <TextField
        name={name}
        variant={variant}
        autoComplete="off"
        InputProps={{
          spellCheck: false,
          inputComponent: NumberFormatCustom as any,
          inputProps: {
            decimalScale: isHDDcoinCurrency ? 12 : 3,
            'data-testid': dataTestid,
          },
          endAdornment: dropdownAdornment ? (
            <IconButton onClick={dropdownAdornment}>
              <ArrowDropDownIcon />
            </IconButton>
          ) : (
            <InputAdornment position="end">{currencyCode}</InputAdornment>
          ),
          style: dropdownAdornment ? { paddingRight: '0' } : undefined,
        }}
        label={label}
        {...rest}
      />
      <FormHelperText component="div">
        <Flex alignItems="center" gap={2}>
          {showAmountInBytes && (
            <Flex flexGrow={1} gap={1}>
              {!byte.isZero() && (
                <>
                  <FormatLargeNumber value={byte} />
                  <Box>
                    <Plural value={byte.toNumber()} one="byte" other="bytes" />
                  </Box>
                </>
              )}
            </Flex>
          )}
          {children &&
            children({
              byte,
              value,
            })}
        </Flex>
      </FormHelperText>
    </FormControl>
  );
}
