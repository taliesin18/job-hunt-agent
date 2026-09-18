# Job Hunt Extractor for Microsoft Edge

This local companion extension reads only the active job-listing page when
you click **Extract current job**. It produces a schema-compatible
`JobPosting` JSON record ready for the Job Hunt Agent; the local API validates
it on import, while the complete cleaned page text remains in
`raw_description`, so no requirement is lost.

## Install locally in Edge

1. In Edge, open `edge://extensions`.
2. Turn on **Developer mode**.
3. Select **Load unpacked**, then choose this `edge-extension` folder.
4. Pin **Job Hunt Extractor** from the Extensions menu.

The extension requests access only to the tab you explicitly extract from. It
does not send the job posting to a service, sign in, apply, or change the page.

## Use it

1. Open the job's full details page in Edge.
2. Open the extension and choose **Extract current job**.
3. Choose **Copy JSON**.
4. Open the Job Hunt Agent at `http://localhost:8080`, paste into **Paste a
   job description**, then choose **Find match**.

The frontend recognizes the JSON shape and sends it directly to the local API.
That validates the record, retains the source description, and skips the
separate local-LLM parsing pass. Plain-text and URL pastes still follow the
original parser flow.
