# DSJJQFX Interface Guide

This document summarizes the four `http://68.253.2.111/dsjfx` endpoints most commonly used in this project. If a code path depends on this host, read the matching section here before implementing or changing logic.

## Basics

- Base URL: `http://68.253.2.111/dsjfx`
- Covered endpoints:
  - `/plan/treeViewData`
  - `/nature/treeNewViewData`
  - `/case/list`
  - `/srr/list`
- These APIs return business fields that are mostly Chinese in the raw payload. When integrating them into project code, normalize fields into stable internal names in an adapter or script instead of scattering raw field names across business logic.
- Query requests usually rely on an existing login session, cookie, or service-side authenticated context. If code calls these endpoints directly, confirm the authentication requirement first.

## 1. `/plan/treeViewData`

### Purpose

Returns the plan or case-category tree structure. Typical uses:

- Tree selectors in the frontend
- Mapping between plan IDs, names, and tags
- Initial data for plan-based filtering conditions

### Request

- Method: `GET`
- URL: `http://68.253.2.111/dsjfx/plan/treeViewData`

### Response shape

The response is an array of tree nodes. Common fields:

- `id`: node ID
- `pId`: parent node ID
- `name`: node display name
- `pinYin`: pinyin
- `firstChar`: pinyin initials
- `title`: usually `name(id)`
- `tag`: business tag code
- `open`, `checked`, `nocheck`: tree widget state fields

### Usage notes

- This is metadata, not a detail list.
- If the code only needs mapping data, cache the result instead of re-fetching repeatedly.
- In most cases, `id` and `name` are the only fields the business layer needs.

## 2. `/nature/treeNewViewData`

### Purpose

Returns the incident nature or category tree. Typical uses:

- Incident-nature selectors
- Mapping from category code to display name
- Initial tree data for category-based filtering

### Request

- Method: `GET`
- URL: `http://68.253.2.111/dsjfx/nature/treeNewViewData`

### Response shape

The response is an array of tree nodes. Common fields:

- `id`: category code such as `01` or `0101`
- `pId`: parent category code
- `name`: category name
- `pinYin`: pinyin
- `firstChar`: pinyin initials
- `title`: usually `name(code)`
- `open`, `checked`, `nocheck`: tree widget state fields

### Usage notes

- This is also a metadata API, similar to `/plan/treeViewData`.
- If filtering by incident category, store the `id` as the real value and use `name` only for display.
- The hierarchy is suitable for cascaded selection or cached tree rendering.

## 3. `/case/list`

### Purpose

Returns detailed incident rows. This is the most important endpoint for theme monitoring and several custom task flows. The usual pattern is time-window fetch, paginated retrieval, and project-side secondary filtering.

### Request

- Method: `POST`
- URL: `http://68.253.2.111/dsjfx/case/list`

### Common request parameters

The project most often uses these parameters:

- `beginDate`: query start time, format `YYYY-MM-DD HH:mm:ss`
- `endDate`: query end time, format `YYYY-MM-DD HH:mm:ss`
- `pageSize`: page size
- `pageNum`: page number, starting from `1`
- `orderByColumn`: sort column, commonly `callTime`
- `isAsc`: sort direction, commonly `desc`

Common fields that are usually left empty or set to "all":

- `newCaseSourceNo` / `newCaseSource`
- `dutyDeptNo` / `dutyDeptName`
- `newCharaSubclassNo` / `newCharaSubclass`
- `newOriCharaSubclassNo` / `newOriCharaSubclass`
- `caseNo`
- `callerName`
- `callerPhone`
- `occurAddress`
- `caseContents`
- `replies`
- `caseMarkNo` / `caseMark`

### Common response structure

Top-level fields usually include:

- `code`: API result code, where `0` means success
- `total`: total record count
- `rows`: array of detail rows for the current page

Frequently used fields inside `rows`:

- `caseNo`: incident number
- `callTime`: call time
- `occurTime`: occurrence time
- `dutyDeptNo` / `dutyDeptName`: handling department code and name
- `cmdId` / `cmdName`: upper-level department code and name
- `occurAddress`: occurrence address
- `caseContents`: incident content
- `replies`: handling feedback
- `callerName` / `callerPhone`: caller information
- `newCharaSubclass` / `newCharaSubclassName`: new fine-grained category code and name
- `newOriCharaSubclass` / `newOriCharaSubclassName`: original fine-grained category code and name

### Usage notes

- This is the primary detail endpoint and should usually be driven by a time window plus pagination.
- The recommended pattern is: fetch broadly first, then apply topic or task-specific filtering in project code.
- For large result sets, increase `pageSize` and set an explicit page cap to avoid unbounded pagination.
- If downstream code needs stable template or deduplication variables, normalize them in the adapter layer, for example `event_key`, `case_no`, `call_time`, or `alarmTime`.

## 4. `/srr/list`

### Purpose

Returns aggregated statistical data rather than incident details. Typical uses:

- Statistical dashboards
- Grouped summaries by department
- Period-over-period trend views

### Request

- Method: `POST`
- URL: `http://68.253.2.111/dsjfx/srr/list`

### Common request parameters

- `params[startTime]` / `params[endTime]`: current period
- `params[y2yStartTime]` / `params[y2yEndTime]`: year-over-year comparison period
- `params[m2mStartTime]` / `params[m2mEndTime]`: month-over-month comparison period
- `groupField`: grouping key, example `duty_dept_no`
- `caseLevel`
- `charaNo`
- `chara`
- `charaType`
- `charaLevel`
- `dutyDeptNo` / `dutyDeptName`
- `newRecvType` / `newRecvTypeName`
- `newCaseSourceNo` / `newCaseSource`
- `caseContents`
- `replies`

### Common response structure

Top-level fields usually include:

- `code`: API result code, where `0` means success
- `total`: number of grouped result rows
- `rows`: array of grouped statistics

Frequently used fields inside `rows`:

- `code`: grouping code
- `name`: grouping name
- `presentCycle`: current-period count
- `upperY2yCycle`: year-over-year comparison count
- `y2yProportion`: year-over-year change
- `upperM2mCycle`: month-over-month comparison count
- `m2mProportion`: month-over-month change

### Usage notes

- This endpoint is suitable for dashboards, not for per-incident SMS notification.
- If the requirement is to filter incident rows by keyword, address, or feedback content, prefer `/case/list`.
- If the requirement is to compare total incident volume by department and period, then `/srr/list` is the better fit.

## Endpoint Selection

When code touches `http://68.253.2.111`, use this rule of thumb:

- Need tree metadata: use `/plan/treeViewData` or `/nature/treeNewViewData`
- Need per-incident detail rows: use `/case/list`
- Need aggregate statistics: use `/srr/list`

If one feature needs both metadata and detail data, the usual flow is:

1. Load the category or plan tree from the matching tree endpoint
2. Fetch detail rows from `/case/list`
3. Apply topic filtering or notification logic in project code
