import os

bundles = {}


class PoorManResourceBundle:
    bundle = None
    active_locale = None
    
    def __init__(self, locale:str='JA'):
        """
        Initializes a PoorManResourceBundle instance with a specified locale.
    
        This constructor initializes the resource bundle for the given locale by
        loading all available bundles and selecting the one corresponding to the
        specified locale. If the locale is not found, the bundle remains uninitialized.
    
        :param locale: The locale code to use for the resource bundle. Defaults to 'ja'.
        """
        
        self.load_bundles()
        self.bundle = bundles.get(locale.upper());
        self.active_locale = locale

    def load_bundle(self, bundle_file, locale):
        """
        Loads a resource bundle file for a specific locale.
    
        This method reads a file containing key-value pairs, processes its content,
        and stores the localized strings in the global `bundles` dictionary under
        the specified locale. Blank lines and comment lines (starting with `#`) 
        in the file are skipped. The key-value pairs can be separated by either 
        `=` or `:`.
    
        :param bundle_file: The name of the bundle file to load.
        :param locale: The locale code associated with the bundle file.
        """
        print(f'Loading bundle "{locale}" from file "{bundle_file}"...')
        
        with open('resources/' + bundle_file, 'r', encoding="utf-8") as f:
            locale_bundle = {}
            
            for line in f.readlines():
                line = line.strip()
                
                if not line:  # Skip blank lines
                    continue
                
                if line.startswith("#"):  # Skip comments
                    continue
            
                # Determine the split character
                split_char = "=" if "=" in line else ":"
                
                key = line[:line.find(split_char)].strip()
                value = line[line.find(split_char) + 1:].strip()
                
                locale_bundle[key] = value
            
            bundles[locale] = locale_bundle
            
        print(f'Bundle "{locale}" loaded.')

    def load_bundles(self):
        """
        Loads all resource bundle files from the 'resources' directory.
    
        This method iterates through the files in the specified directory and loads
        only those that match the naming pattern "messages_<locale>.properties".
        For each valid file, it extracts the locale from the file name and calls
        the `load_bundle` method to process its content. Files that do not match
        the naming pattern are skipped.
    
        :raises FileNotFoundError: If the 'resources' directory does not exist.
        """
        bundle_files = [i for i in os.listdir('resources') if i.endswith('.properties') == True]
        
        for bundle_file in bundle_files:
            if bundle_file.startswith("messages_") and bundle_file.endswith(".properties"):
                
                locale = bundle_file[len("messages_"):-len(".properties")]
                self.load_bundle(bundle_file, locale.upper())
                
            else:
                print(f'File "{bundle_file}" is not a valid bundle file. Skipping...')
        
    def get_text(self, key: str, *args):
        """
        Formats a message using a key and a variable number of arguments.
    
        :param key: The message template with placeholders in the format "{<index>}".
        :param args: The arguments to replace the placeholders.
        :return: The formatted message.
        :raises ValueError: If there are more arguments than placeholders.
        """
        try:
            if self.bundle != None:
            
                message = self.bundle.get(key)
                
                if message is None :
                    raise ValueError(f"No i18n message for key '{key}' in bundle '{self.active_locale}'")
                
                if len(args) == 0 :
                    return message
                
                placeholder_count = message.count("{")
    
                # Check if there are more arguments than placeholders
                if len(args) > placeholder_count:
                    raise ValueError("Too many arguments provided for the placeholders in the key.")
        
                # Format the message
                return message.format(*args)
            else:
                    raise RuntimeError('Bundle not initialized')
        except IndexError as e:
            raise ValueError("Not enough arguments provided for the placeholders in the key.") from e

    def get_available_bundles(self):
        """
        Retrieves a list of all available locale bundles.
    
        This method returns the keys of the global `bundles` dictionary, which
        represent the locales for which resource bundles have been loaded.
    
        :return: A list of available locale codes.
        """
        return list(bundles.keys())


if __name__ == '__main__':
    a = PoorManResourceBundle(locale='JA')        
        
        
