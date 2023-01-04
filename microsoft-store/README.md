# submit-to-microsoft-store.py

A client for submitting KDE apps to the Microsoft Store

## Setup

Create a virtual environment and install the requirements.
```
python3 -m venv .venv-ms-store
. .venv-ms-store/bin/activate
pip3 install -r requirements.txt
```

## Usage

Usually, this script will be run by the CI. The CI needs to provide the credentials
for accessing the Microsoft Store submission API in the environment variables
`MICROSTORE_TENANT_ID`, `MICROSTORE_CLIENT_ID`, `MICROSTORE_CLIENT_SECRET`.
See [Complete prerequisites for using the Microsoft Store submission API](https://learn.microsoft.com/en-us/windows/uwp/monetize/create-and-manage-submissions-using-windows-store-services#prerequisites)
for information how to get those credentials.

To submit an app run
```
python3 submit-to-microsoft-store.py <appstreamId> <appxuploadFile>
```
where *appstreamId* is the AppStream ID of the app (e.g. org.kde.neochat) and
*appxuploadFile* is the path of an .appxupload built by the CI.

If the AppStream data does not yet contain the URL for the Microsoft Store (e.g.
before the first public release), then you have to provide the Store ID of the
app with the `--store-id` option.

### Notes

The first submission has to be made via the
[Microsoft Partner Center](https://partner.microsoft.com/en-us/dashboard/windows/overview)
to fill out the age restriction questionnaire. There are also other values that
cannot be changed with the submission API or that cannot be filled automatically
with information from the AppStream data, e.g. the list of features.
It might make sense to make the app not publicly visible initially.
Once everything looks good for a public release, a new
submission can simply be created via the Partner Center which just changes the
visibility to public.

For a test run which doesn't change anything in the Microsoft Store use the
`--dry-run` option. This will output the data that would be submitted.<br>
**Warning:** The output can contain confidential information, e.g. if you have
provided test credentials in the notes for submission.

The script updates the information of the last published submission with the
information found in the AppStream data of the app (including translations).
The Store ID is extracted from the Microsoft Store URL of the app which is
stored in the AppStream data as custom value with key `KDE::windows_store`.
The script will add a store listing for each language with a non-empty Description
in the AppStream data. By default, existing listing values are overwritten with
corresponding AppStream values for a language. To keep existing non-empty values
use the `--keep` option with a comma-separated list of the values to keep.

| Listing Value             | AppStream Value       | Notes |
| ---                       | ---                   | ---   |
| copyrightAndTrademarkInfo | -                     |       |
| description               | `description`         | Uses value for language. |
| keywords                  | `keywords`            | Uses values for language. |
| licenseTerms              | `project_license`     |       |
| supportContact            | `url type="contact"`  |       |
| websiteUrl                | `url type="homepage"` |       |
| features                  | -                     |       |
| releaseNotes              | `releases`            | Uses `description` of first `release` for language (with fallback to English). |
| images                    | `screenshots`         | Uses all `screenshot` of type `default`; marks files with "mobile" in the name as MobileScreenshot; uses `caption` for language as image description. |
| recommendedHardware       | -                     |       |
| minimumHardware           | -                     |       |
| title                     | -                     | must be a reserved name; we keep what's there or use the primaryName of the [Application resource](https://learn.microsoft.com/en-us/windows/uwp/monetize/get-app-data#application-resource) |
| shortDescription          | `summary`             | Uses value for language. |
| shortTitle                | -                     |       |
| sortTitle                 | -                     |       |
| voiceTitle                | -                     |       |
| devStudio                 | `developer_name`      | Uses value for language (with fallback to English). |

See [Base listing resource](https://learn.microsoft.com/en-us/windows/uwp/monetize/manage-app-submissions#base-listing-object)
for a description of the listing values. Listing values which have no equivalent
in the AppStream data can be filled out manually in the
[Microsoft Partner Center](https://partner.microsoft.com/en-us/dashboard/windows/overview).
If you want to make sure that those values are not overwritten once AppStream
provides this information and the script has been updated, then add those
values to the list of values to keep.
