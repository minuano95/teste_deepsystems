import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from pymongo import MongoClient
from datetime import datetime

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
client = MongoClient('mongodb://localhost:27017/')
db = client['telegram_bot']
users = db['users']

# Start command handler
async def start(update: Update, context: CallbackContext) -> None:
    """Handles the /start command. Initializes a user in the database if they don't exist and presents them with a menu."""
    user_id = update.message.from_user.id
    if not users.find_one({"user_id": user_id}):
        # Insert a new user record with initial balance and no last transaction
        users.insert_one({"user_id": user_id, "balance": 0, "last_transaction": None})
    
    keyboard = [
        [InlineKeyboardButton("Check Balance", callback_data='check_balance')],
        [InlineKeyboardButton("Deposit", callback_data='deposit')],
        [InlineKeyboardButton("Withdraw", callback_data='withdraw')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Welcome to the Mock Bank Bot! Choose an option:', reply_markup=reply_markup)

# Callback query handler
async def button(update: Update, context: CallbackContext) -> None:
    """Handles button clicks from the inline keyboard."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = users.find_one({"user_id": user_id})
    
    if query.data == 'check_balance':
        # Retrieve the user's last transaction if available
        last_transaction = user.get('last_transaction', 'No transactions yet')
        
        if last_transaction != 'No transactions yet':
            transaction_details = last_transaction.split(' on ')
            transaction_time_str = transaction_details[-1]
            transaction_time = datetime.strptime(transaction_time_str, '%Y-%m-%d %H:%M:%S.%f')
            formatted_time = transaction_time.strftime('%d/%m/%Y %H:%M:%S')
            formatted_last_transaction = f"{transaction_details[0]} on {formatted_time}"
        else:
            formatted_last_transaction = 'No transactions yet'
        
        await query.edit_message_text(text=f"Your balance is: {user['balance']}\nLast transaction: {formatted_last_transaction}")
    
    elif query.data == 'deposit':
        # Set the action to deposit
        context.user_data['action'] = 'deposit'
        await query.edit_message_text(text="How much would you like to deposit?")

    elif query.data == 'withdraw':
        # Set the action to withdraw
        context.user_data['action'] = 'withdraw'
        await query.edit_message_text(text="How much would you like to withdraw?")

async def handle_amount(update: Update, context: CallbackContext) -> None:
    """Handles the user's input for deposit and withdrawal amounts."""
    # Check if the user is in a confirmation state
    if context.user_data.get('confirming'):
        await handle_invalid_response(update, context)
        return

    user_id = update.message.from_user.id
    user = users.find_one({"user_id": user_id})

    # Check if the action has been set
    action = context.user_data.get('action')
    if action is None:
        await update.message.reply_text("Please start the transaction again.")
        return

    try:
        # Attempt to convert the user's input to an integer
        amount = int(update.message.text.strip())

        # Check if the amount is greater than zero
        if amount <= 0:
            await update.message.reply_text("Please enter a value greater than 0.")
            return

        context.user_data['amount'] = amount  # Store the amount in user data
        await update.message.reply_text(f"You entered: {amount}. Type 'confirm' to proceed or 'cancel' to cancel.")
        
        # Set a confirmation state
        context.user_data['confirming'] = True

    except ValueError:
        await update.message.reply_text("Please enter a valid number.")

async def handle_confirmation(update: Update, context: CallbackContext) -> None:
    """Handles user confirmation for transactions."""
    # Check if the user is in a confirmation state
    if context.user_data.get('confirming'):
        confirmation_input = update.message.text.strip().lower()

        user_id = update.message.from_user.id
        user = users.find_one({"user_id": user_id})
        action = context.user_data.get('action')
        amount = context.user_data.get('amount')

        # Process the confirmation
        if confirmation_input == 'confirm':
            if action == 'deposit':
                new_balance = user['balance'] + amount
                users.update_one({"user_id": user_id}, {"$set": {"balance": new_balance, "last_transaction": f"Deposited {amount} on {datetime.now()}"}})
                await update.message.reply_text(f"Deposited {amount}. New balance: {new_balance}")
                
            elif action == 'withdraw':
                if amount > user['balance']:
                    await update.message.reply_text("Insufficient balance.")
                elif amount <= 0:
                    await update.message.reply_text("Please enter a value greater than 0.")
                else:
                    new_balance = user['balance'] - amount
                    users.update_one({"user_id": user_id}, {"$set": {"balance": new_balance, "last_transaction": f"Withdrew {amount} on {datetime.now()}"}})
                    await update.message.reply_text(f"Withdrew {amount}. New balance: {new_balance}")
            
            # Reset the confirmation state
            context.user_data['confirming'] = False

        elif confirmation_input == 'cancel':
            await update.message.reply_text("Transaction cancelled.")
            context.user_data['confirming'] = False  # Reset the state
            # Clear the action and amount
            context.user_data['action'] = None
            context.user_data['amount'] = None

        else:
            await update.message.reply_text("Please respond with 'confirm' or 'cancel'.")
    else:
        await update.message.reply_text("Please start a transaction first.")

# Function to handle invalid responses
async def handle_invalid_response(update: Update, context: CallbackContext) -> None:
    """Handles invalid responses when the user is expected to confirm."""
    # Check if the user is in a confirmation state
    if context.user_data.get('confirming'):
        await update.message.reply_text("Please respond with 'confirm' or 'cancel'.")

# Main function to start the bot
def main() -> None:
    """Main function to set up and run the Telegram bot."""
    application = Application.builder().token("TOKEN").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    
    # Capture only messages that are not 'Confirm' or 'Cancel'
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(confirm|cancel)$'), handle_amount))
    
    # Capture confirmation messages (Confirm/Cancel)
    application.add_handler(MessageHandler(filters.Regex('^(confirm|cancel)$'), handle_confirmation))

    # Capture invalid responses (anything that is not 'confirm' or 'cancel')
    application.add_handler(MessageHandler(filters.TEXT, handle_invalid_response))

    application.run_polling()

if __name__ == '__main__':
    main()
