---
id: polling_status
title: Polling for a Status Update
sidebar_label: Polling for a Status Update
---

The merchant site can poll for a current transaction status to Paynow at any point, but it should only be done in the following two scenarios:

- The merchant site receives an important status update from Paynow and wants to poll Paynow to confirm the status.
- The merchant site is going to delete old or unpaid transactions, before doing this the merchant site should poll Paynow and confirm the transaction status before deleting it from their system.

To poll for a transaction status the merchant site should perform an empty HTTP POST to the pollurl sent by Paynow in transaction initiation or status update.  Paynow will reply with a string formatted as an HTTP POST, i.e. each field separated by a & and Key Value pairs separated by an = and all Values URL Encoded, with the same fields as if it were posting a result to the merchant site.

An example of the result from Paynow is shown below:
```http
reference=ABC123&paynowreference=123456&amount=1.00&status=Awaiting+Delivery&pollurl=https%3A%2F%2Fwww.paynow.co.zw%2FInterface%2FCheckPayment%2F%3Fguid%3D9f24be04-f4a6-4dff-8ab5-455263ba7b6b&hash=785659BF4970D86C4F5B9357473B53F43AF3FFA28E6A622D8EF83B69B68E5464C6BBD0F4187D8C6FB31B71DB3700C415B2434DB8D6F670CDBB809502C339AB3C
```
## Using Merchant Trace
When making use of Express Checkout functionality on Paynow, the merchant should supply a **merchanttrace** field value in their request message (up to 32 characters in length, unique per merchant)

The merchant trace reference is stored against the transaction and will allow the merchant to query the status of a transaction in the event that they were unable to receive the **pollurl** in the response from Paynow e.g. network interruption or timeout.

A trace query can be made by request in the form of an HTTP POST to the URL:

[https://www.paynow.co.zw/interface/trace](https://www.paynow.co.zw/interface/trace)

The HTTP POST should include the following fields:

**Field**|**Data Type**|**Description**
-----|-----|-----
id|Integer|Integration ID shown to the merchant in the “3rd Party Site or Link Profile” area of “Receive Payment Links” section of “Sell or Receive” on Paynow.
merchanttrace|String|The original merchanttrace that was specified when the merchant initiated the transaction being traced.
status|String|Should be set to “Message”.
hash|String|Details of Hash generation are provided in the [Generating Hash](generating_hash.md) section.

### Transaction Found
If the trace successfully locates a transaction, Paynow will reply with a standard [Status Update](#status-update-from-paynow) message showing the status of the transaction

### Transaction Not Found
If a transaction is not found during a trace, the status NotFound will be returned. For example:

```http
status=NotFound&hash=2D72F08C4F34B99DEC391E2A24F24C2598060B9F6D63CB0B961FEDAE7D7D69D6321931A18F8E1E0268DE5A4F72B5D76E5A8A767C810180D9D5AC921B444B51BA
```

### Error

If there was an error during a trace operation, the error details will be returned. For example:

```http
status=Error&error=Trace+failed
```

>**N.B.** A trace error **does not** necessarily mean that the transaction was not found