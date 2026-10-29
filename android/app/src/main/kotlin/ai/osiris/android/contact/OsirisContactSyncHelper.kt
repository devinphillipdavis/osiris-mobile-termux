package ai.osiris.android.contact

import android.content.ContentProviderOperation
import android.content.Context
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.provider.ContactsContract
import android.util.Log

object OsirisContactSyncHelper {

    private const val TAG = "OsirisContactSync"
    const val CONTACT_NAME = "OSIRIS Sovereign AI"
    const val CONTACT_PHONE = "+1-800-674-7471"
    const val CONTACT_EMAIL = "osiris@node-beta.local"
    const val CONTACT_NOTE = "OSIRIS Sovereign Presence: Node Beta & Mobile Interface"

    fun isContactSynchronized(context: Context): Boolean {
        return try {
            val uri: Uri = ContactsContract.Data.CONTENT_URI
            val projection = arrayOf(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
            val selection = "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} = ?"
            val selectionArgs = arrayOf(CONTACT_NAME)

            val cursor: Cursor? = context.contentResolver.query(uri, projection, selection, selectionArgs, null)
            val exists = (cursor?.count ?: 0) > 0
            cursor?.close()
            exists
        } catch (e: Exception) {
            Log.w(TAG, "Failed to query ContactsProvider: ${e.message}")
            false
        }
    }

    fun syncContactToProvider(context: Context): Boolean {
        return try {
            if (isContactSynchronized(context)) {
                Log.d(TAG, "OSIRIS contact already synchronized.")
                return true
            }

            val ops = ArrayList<ContentProviderOperation>()

            // 1. RawContact insert
            val rawContactIndex = ops.size
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.RawContacts.CONTENT_URI)
                    .withValue(ContactsContract.RawContacts.ACCOUNT_TYPE, null)
                    .withValue(ContactsContract.RawContacts.ACCOUNT_NAME, null)
                    .build()
            )

            // 2. Display Name
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                    .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, rawContactIndex)
                    .withValue(ContactsContract.Data.MIMETYPE, ContactsContract.CommonDataKinds.StructuredName.CONTENT_ITEM_TYPE)
                    .withValue(ContactsContract.CommonDataKinds.StructuredName.DISPLAY_NAME, CONTACT_NAME)
                    .build()
            )

            // 3. Phone Number
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                    .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, rawContactIndex)
                    .withValue(ContactsContract.Data.MIMETYPE, ContactsContract.CommonDataKinds.Phone.CONTENT_ITEM_TYPE)
                    .withValue(ContactsContract.CommonDataKinds.Phone.NUMBER, CONTACT_PHONE)
                    .withValue(ContactsContract.CommonDataKinds.Phone.TYPE, ContactsContract.CommonDataKinds.Phone.TYPE_WORK)
                    .build()
            )

            // 4. Email
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                    .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, rawContactIndex)
                    .withValue(ContactsContract.Data.MIMETYPE, ContactsContract.CommonDataKinds.Email.CONTENT_ITEM_TYPE)
                    .withValue(ContactsContract.CommonDataKinds.Email.ADDRESS, CONTACT_EMAIL)
                    .withValue(ContactsContract.CommonDataKinds.Email.TYPE, ContactsContract.CommonDataKinds.Email.TYPE_WORK)
                    .build()
            )

            // 5. Note / Metadata
            ops.add(
                ContentProviderOperation.newInsert(ContactsContract.Data.CONTENT_URI)
                    .withValueBackReference(ContactsContract.Data.RAW_CONTACT_ID, rawContactIndex)
                    .withValue(ContactsContract.Data.MIMETYPE, ContactsContract.CommonDataKinds.Note.CONTENT_ITEM_TYPE)
                    .withValue(ContactsContract.CommonDataKinds.Note.NOTE, CONTACT_NOTE)
                    .build()
            )

            context.contentResolver.applyBatch(ContactsContract.AUTHORITY, ops)
            Log.i(TAG, "OSIRIS contact created in system ContactsProvider.")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error synchronizing OSIRIS contact", e)
            false
        }
    }

    fun createInsertContactIntent(): Intent {
        return Intent(Intent.ACTION_INSERT, ContactsContract.Contacts.CONTENT_URI).apply {
            putExtra(ContactsContract.Intents.Insert.NAME, CONTACT_NAME)
            putExtra(ContactsContract.Intents.Insert.PHONE, CONTACT_PHONE)
            putExtra(ContactsContract.Intents.Insert.EMAIL, CONTACT_EMAIL)
            putExtra(ContactsContract.Intents.Insert.NOTES, CONTACT_NOTE)
        }
    }
}
