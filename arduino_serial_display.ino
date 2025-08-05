/*
 * Arduino Serial Display for Facial Recognition
 * This code receives names via serial and displays them on an LCD
 */

#include <LiquidCrystal.h>

// Initialize LCD (adjust pins as needed for your setup)
// LCD pins: RS=12, E=11, D4=5, D5=4, D6=3, D7=2
LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

String receivedName = "";
String currentDisplay = "Waiting...";
unsigned long lastUpdate = 0;

void setup() {
  // Initialize serial communication
  Serial.begin(9600);
  
  // Initialize LCD
  lcd.begin(16, 2);  // 16 columns, 2 rows
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Facial Recognition");
  lcd.setCursor(0, 1);
  lcd.print("System Ready");
  
  delay(2000);
  
  // Clear and show waiting message
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Current Person:");
  lcd.setCursor(0, 1);
  lcd.print("Waiting...");
  
  Serial.println("Arduino ready to receive names");
}

void loop() {
  // Check if serial data is available
  if (Serial.available() > 0) {
    receivedName = Serial.readStringUntil('\n');
    receivedName.trim();  // Remove any whitespace
    
    // Only update if the name is different
    if (receivedName != currentDisplay && receivedName.length() > 0) {
      currentDisplay = receivedName;
      
      // Update LCD display
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Current Person:");
      lcd.setCursor(0, 1);
      
      // Handle long names
      if (currentDisplay.length() > 16) {
        lcd.print(currentDisplay.substring(0, 16));
      } else {
        lcd.print(currentDisplay);
      }
      
      // Send confirmation back
      Serial.print("Displayed: ");
      Serial.println(currentDisplay);
      
      lastUpdate = millis();
    }
  }
  
  // Optional: Show "Waiting..." if no updates for 30 seconds
  if (millis() - lastUpdate > 30000 && currentDisplay != "Waiting...") {
    currentDisplay = "Waiting...";
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Current Person:");
    lcd.setCursor(0, 1);
    lcd.print("Waiting...");
  }
  
  delay(100);  // Small delay to prevent overwhelming the serial
} 