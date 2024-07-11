import bcrypt
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import IntegrityError, OperationalError
import streamlit as st
from PIL import Image as PILImage
import pillow_heif
import os
import random
import sys
import shutil
import zipfile
import imageio.v3 as iio  # imageio の v3 を使用
import io

# Increase recursion limit
sys.setrecursionlimit(5000)

# Set up database
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    images = relationship('Image', back_populates='user')
    dislikes = relationship('Dislike', back_populates='user')
    favorites = relationship('Favorite', back_populates='user')

class Image(Base):
    __tablename__ = 'images'
    id = Column(Integer, primary_key=True)
    category = Column(String)
    path = Column(String)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='images')

class Dislike(Base):
    __tablename__ = 'dislikes'
    id = Column(Integer, primary_key=True)
    top_id = Column(Integer, ForeignKey('images.id'))
    bottom_id = Column(Integer, ForeignKey('images.id'))
    shoes_id = Column(Integer, ForeignKey('images.id'), nullable=True)
    accessory_id = Column(Integer, ForeignKey('images.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='dislikes')

class Favorite(Base):
    __tablename__ = 'favorites'
    id = Column(Integer, primary_key=True)
    top_id = Column(Integer, ForeignKey('images.id'))
    bottom_id = Column(Integer, ForeignKey('images.id'))
    shoes_id = Column(Integer, ForeignKey('images.id'), nullable=True)
    accessory_id = Column(Integer, ForeignKey('images.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User', back_populates='favorites')

# Create database
engine = create_engine('sqlite:///fashion.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Directory for uploaded images and backups
UPLOAD_DIR = 'uploads'
BACKUP_DIR = 'backups'
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
if not os.path.exists(BACKUP_DIR):
    os.makedirs(BACKUP_DIR)

# Initialize session state for buttons
if "dislike_button_clicked" not in st.session_state:
    st.session_state["dislike_button_clicked"] = False

if "favorite_button_clicked" not in st.session_state:
    st.session_state["favorite_button_clicked"] = False

if "logged_in_user" not in st.session_state:
    st.session_state["logged_in_user"] = None

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(hashed_password, plain_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def authenticate(username, password):
    user = session.query(User).filter_by(username=username).first()
    if user and check_password(user.password, password):
        return user
    return None

def register(username, password):
    hashed_password = hash_password(password)
    new_user = User(username=username, password=hashed_password)
    try:
        session.add(new_user)
        session.commit()
        return new_user
    except IntegrityError:
        session.rollback()
        return None

def create_backup():
    backup_file = os.path.join(BACKUP_DIR, 'fashion_backup.zip')
    with zipfile.ZipFile(backup_file, 'w') as zipf:
        # Add database file to the zip
        zipf.write('fashion.db', os.path.basename('fashion.db'))
        # Add user-specific uploaded images to the zip
        for root, dirs, files in os.walk(UPLOAD_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, UPLOAD_DIR)
                zipf.write(file_path, arcname)
    return backup_file

def restore_backup(backup_file):
    with zipfile.ZipFile(backup_file, 'r') as zipf:
        # Extract all files in the ZIP to a temporary directory
        temp_dir = os.path.join(BACKUP_DIR, 'temp_restore')
        zipf.extractall(temp_dir)
        
        # Print the contents of the temporary directory for debugging
        for root, dirs, files in os.walk(temp_dir):
            print("Root:", root)
            print("Directories:", dirs)
            print("Files:", files)
        
        # Move the extracted database file to the current directory
        db_path = os.path.join(temp_dir, 'fashion.db')
        if os.path.exists(db_path):
            shutil.move(db_path, 'fashion.db')

        # Process the extracted uploads directory
        for user_dir in os.listdir(temp_dir):
            user_dir_path = os.path.join(temp_dir, user_dir)
            if os.path.isdir(user_dir_path) and user_dir != 'fashion.db':
                user_upload_dir = os.path.join(UPLOAD_DIR, user_dir)
                if not os.path.exists(user_upload_dir):
                    os.makedirs(user_upload_dir)
                for root, dirs, files in os.walk(user_dir_path):
                    for file_ in files:
                        # Source file path
                        src_file = os.path.join(root, file_)
                        # Relative path from the extracted user directory
                        relative_path = os.path.relpath(src_file, user_dir_path)
                        # Destination file path
                        dst_file = os.path.join(user_upload_dir, relative_path)
                        # Create the destination directory if it doesn't exist
                        dst_dir = os.path.dirname(dst_file)
                        if not os.path.exists(dst_dir):
                            os.makedirs(dst_dir)
                        # Copy the file
                        shutil.copy2(src_file, dst_file)

        # Clean up the temporary directory
        shutil.rmtree(temp_dir)

def hash_existing_passwords():
    users = session.query(User).all()
    for user in users:
        if not user.password.startswith('$2b$'):
            hashed_password = hash_password(user.password)
            user.password = hashed_password
    session.commit()

# Hash existing passwords
hash_existing_passwords()

# Streamlit app
st.title('ファッション提案アプリ')

if st.session_state["logged_in_user"] is None:
    st.header("ログイン")
    username = st.text_input("ユーザー名")
    password = st.text_input("パスワード", type="password")
    if st.button("ログイン"):
        user = authenticate(username, password)
        if user:
            st.session_state["logged_in_user"] = user
            st.success("ログイン成功")
            st.rerun()
        else:
            st.error("ログイン失敗")
    
    st.header("新規登録")
    new_username = st.text_input("新しいユーザー名")
    new_password = st.text_input("新しいパスワード", type="password")
    if st.button("登録"):
        new_user = register(new_username, new_password)
        if new_user:
            st.success("登録成功")
        else:
            st.error("ユーザー名は既に存在します")
else:
    user = st.session_state["logged_in_user"]
    st.sidebar.text(f"ログイン中: {user.username}")
    if st.sidebar.button("ログアウト"):
        st.session_state["logged_in_user"] = None
        st.rerun()

    # Page navigation
    page = st.sidebar.selectbox('ページを選択', ['画像をアップロード', 'コーディネート提案', 'お気に入りの編集', '嫌いな組み合わせの編集', 'データベースバックアップ'])

    def load_images_from_directory():
        """
        Load images from the upload directory into the database if not already present.
        """
        user_upload_dir = os.path.join(UPLOAD_DIR, user.username)
        if not os.path.exists(user_upload_dir):
            os.makedirs(user_upload_dir)
        
        for file_name in os.listdir(user_upload_dir):
            file_path = os.path.join(user_upload_dir, file_name)
            if not session.query(Image).filter_by(path=file_path, user_id=user.id).first():
                category = '未分類'  # Default category if not assigned
                new_image = Image(category=category.lower(), path=file_path, user_id=user.id)
                session.add(new_image)
        session.commit()

    def check_dislike_exists(top_id, bottom_id, shoes_id, accessory_id):
        return session.query(Dislike).filter_by(
            top_id=top_id, bottom_id=bottom_id, shoes_id=shoes_id, accessory_id=accessory_id, user_id=user.id
        ).first() is not None

    def check_favorite_exists(top_id, bottom_id, shoes_id, accessory_id):
        return session.query(Favorite).filter_by(
            top_id=top_id, bottom_id=bottom_id, shoes_id=shoes_id, accessory_id=accessory_id, user_id=user.id
        ).first() is not None

    if page == '画像をアップロード':
        # Image upload
        st.header('画像をアップロード')
        category = st.selectbox('カテゴリー', ['top', 'bottom', 'shoes', 'accessory'])
        uploaded_file = st.file_uploader("画像を選択...", type=["jpg", "png", "jpeg", "heic"])

        if uploaded_file is not None:
            try:
                # Display the uploaded file information
                st.write(f"アップロードされたファイル: {uploaded_file.name}")
                # HEICサポートを追加
                pillow_heif.register_heif_opener()

                file_name = uploaded_file.name.lower()

                # ファイルがHEIC形式であるかどうかをチェック
                if file_name.endswith('.heic'):
                    # ファイルをバイナリモードで読み取り、BytesIOオブジェクトに変換
                    uploaded_file_bytes = uploaded_file.read()
                    byte_stream = io.BytesIO(uploaded_file_bytes)
                    img = PILImage.open(byte_stream)
                else:
                    # 他の形式の場合もバイナリモードで読み取り、BytesIOオブジェクトに変換
                    uploaded_file_bytes = uploaded_file.read()
                    byte_stream = io.BytesIO(uploaded_file_bytes)
                    img = PILImage.open(byte_stream)
                user_upload_dir = os.path.join(UPLOAD_DIR, user.username)
                if not os.path.exists(user_upload_dir):
                    os.makedirs(user_upload_dir)

                file_path = os.path.join(user_upload_dir, uploaded_file.name)

                # Save the uploaded file to the server
                img.save(file_path)
                new_image = Image(category=category.lower(), path=file_path, user_id=user.id)
                session.add(new_image)
                session.commit()
                st.success(f"{uploaded_file.name} を {category} カテゴリーにアップロードしました。")
            except Exception as e:
                st.error(f"ファイルのアップロードエラー: {e}")
                st.error(f"デバッグ情報: {uploaded_file}, {file_path}")

        # Uploaded images
        st.header('アップロードされた画像')
        try:
            images = session.query(Image).filter_by(user_id=user.id).all()
            st.write(f"デバッグ情報: 画像の数: {len(images)}")
        except Exception as e:
            st.error(f"データベースクエリエラー: {e}")

        for image in images:
            try:
                st.image(image.path, caption=f"{image.category} (ID: {image.id})", width=150)
            except Exception as e:
                st.error(f"画像の読み込みエラー: {e}")

            if st.button(f'削除 {image.id}', key=f'delete_{image.id}'):
                try:
                    if os.path.exists(image.path):
                        os.remove(image.path)
                    session.delete(image)
                    session.commit()
                    st.success(f"画像 {image.id} を削除しました")
                    st.rerun()
                except Exception as e:
                    st.error(f"画像の削除エラー: {e}")

    elif page == 'コーディネート提案':
        # Random suggestion
        st.header('ランダムなコーディネート提案')

        def get_images_by_category(category):
            return session.query(Image).filter_by(category=category.lower(), user_id=user.id).all()

        def get_random_image(category):
            images = get_images_by_category(category)
            if images:
                return random.choice(images)
            return None

        def is_disliked_combination(top, bottom, shoes, accessory):
            if top and bottom:
                dislike = session.query(Dislike).filter_by(
                    top_id=top.id, bottom_id=bottom.id, shoes_id=shoes.id if shoes else None, accessory_id=accessory.id if accessory else None, user_id=user.id
                ).first()
                return dislike is not None
            return False

        def get_random_suggestion(include_shoes, include_accessory):
            attempts = 0
            max_attempts = 10
            while attempts < max_attempts:
                top = get_random_image('top')
                bottom = get_random_image('bottom')
                shoes = get_random_image('shoes') if include_shoes else None
                accessory = get_random_image('accessory') if include_accessory else None
                if top and bottom and not is_disliked_combination(top, bottom, shoes, accessory):
                    return top, bottom, shoes, accessory
                attempts += 1
            return None, None, None, None

        include_shoes = st.checkbox('shoesを含む', value=True)
        include_accessory = st.checkbox('accessoryを含む', value=True)

        if st.button('コーディネート提案'):
            top, bottom, shoes, accessory = get_random_suggestion(include_shoes, include_accessory)
            st.session_state["top"] = top
            st.session_state["bottom"] = bottom
            st.session_state["shoes"] = shoes
            st.session_state["accessory"] = accessory

        if "top" in st.session_state and st.session_state["top"] and st.session_state["bottom"]:
            st.subheader('top')
            st.image(st.session_state["top"].path, width=150)
            st.subheader('bottom')
            st.image(st.session_state["bottom"].path, width=150)
            if st.session_state["shoes"]:
                st.subheader('shoes')
                st.image(st.session_state["shoes"].path, width=150)
            if st.session_state["accessory"]:
                st.subheader('accessory')
                st.image(st.session_state["accessory"].path, width=150)
        else:
            st.error("新しい提案を生成できませんでした。もっと画像をアップロードするか、嫌いな組み合わせを調整してください。")

        # Feedback
        st.header('フィードバック')
        if st.button('この組み合わせは嫌い'):
            st.session_state["dislike_button_clicked"] = True

        if st.session_state["dislike_button_clicked"]:
            if st.session_state["top"] and st.session_state["bottom"]:
                if not check_dislike_exists(
                    st.session_state["top"].id, st.session_state["bottom"].id,
                    st.session_state["shoes"].id if st.session_state["shoes"] else None,
                    st.session_state["accessory"].id if st.session_state["accessory"] else None
                ):
                    try:
                        new_dislike = Dislike(
                            top_id=st.session_state["top"].id, 
                            bottom_id=st.session_state["bottom"].id, 
                            shoes_id=st.session_state["shoes"].id if st.session_state["shoes"] else None, 
                            accessory_id=st.session_state["accessory"].id if st.session_state["accessory"] else None,
                            user_id=user.id
                        )
                        session.add(new_dislike)
                        session.commit()
                        st.success("組み合わせが嫌いとして記録されました。今後この組み合わせは提案されません。")
                        st.session_state["dislike_button_clicked"] = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"嫌いな組み合わせの保存エラー: {e}")
                else:
                    st.error("この組み合わせは既に嫌いな組み合わせとして登録されています。")

        if st.button('この組み合わせは好き'):
            st.session_state["favorite_button_clicked"] = True

        if st.session_state["favorite_button_clicked"]:
            if st.session_state["top"] and st.session_state["bottom"]:
                if not check_favorite_exists(
                    st.session_state["top"].id, st.session_state["bottom"].id,
                    st.session_state["shoes"].id if st.session_state["shoes"] else None,
                    st.session_state["accessory"].id if st.session_state["accessory"] else None
                ):
                    try:
                        new_favorite = Favorite(
                            top_id=st.session_state["top"].id, 
                            bottom_id=st.session_state["bottom"].id, 
                            shoes_id=st.session_state["shoes"].id if st.session_state["shoes"] else None, 
                            accessory_id=st.session_state["accessory"].id if st.session_state["accessory"] else None,
                            user_id=user.id
                        )
                        session.add(new_favorite)
                        session.commit()
                        st.success("組み合わせが好きとして記録されました。")
                        st.session_state["favorite_button_clicked"] = False
                    except Exception as e:
                        st.error(f"好きな組み合わせの保存エラー: {e}")
                else:
                    st.error("この組み合わせは既に好きな組み合わせとして登録されています。")

    elif page == '嫌いな組み合わせの編集':
        st.header('嫌いな組み合わせ')
        try:
            disliked_combinations = session.query(Dislike).filter_by(user_id=user.id).all()
            st.write(f"デバッグ情報: 嫌いな組み合わせの数: {len(disliked_combinations)}")
        except Exception as e:
            st.error(f"データベースクエリエラー: {e}")

        for dislike in disliked_combinations:
            top_img = session.query(Image).filter_by(id=dislike.top_id).first()
            bottom_img = session.query(Image).filter_by(id=dislike.bottom_id).first()
            shoes_img = session.query(Image).filter_by(id=dislike.shoes_id).first() if dislike.shoes_id else None
            accessory_img = session.query(Image).filter_by(id=dislike.accessory_id).first() if dislike.accessory_id else None

            st.write("嫌いな組み合わせ:")
            try:
                st.image(top_img.path if top_img else '', caption='top', width=150)
                st.image(bottom_img.path if bottom_img else '', caption='bottom', width=150)
                if shoes_img:
                    st.image(shoes_img.path, caption='shoes', width=150)
                if accessory_img:
                    st.image(accessory_img.path, caption='accessory', width=150)
            except Exception as e:
                st.error(f"画像の読み込みエラー: {e}")

            if st.button(f'嫌いを解除 {dislike.id}', key=f'remove_{dislike.id}'):
                session.delete(dislike)
                session.commit()
                st.success(f'嫌い {dislike.id} を解除しました')
                st.rerun()

    elif page == 'お気に入りの編集':
        st.header('好きな組み合わせ')
        try:
            favorite_combinations = session.query(Favorite).filter_by(user_id=user.id).all()
            st.write(f"デバッグ情報: 好きな組み合わせの数: {len(favorite_combinations)}")
        except Exception as e:
            st.error(f"データベースクエリエラー: {e}")

        for favorite in favorite_combinations:
            top_img = session.query(Image).filter_by(id=favorite.top_id).first()
            bottom_img = session.query(Image).filter_by(id=favorite.bottom_id).first()
            shoes_img = session.query(Image).filter_by(id=favorite.shoes_id).first() if favorite.shoes_id else None
            accessory_img = session.query(Image).filter_by(id=favorite.accessory_id).first() if favorite.accessory_id else None

            st.write("好きな組み合わせ:")
            try:
                st.image(top_img.path if top_img else '', caption='top', width=150)
                st.image(bottom_img.path if bottom_img else '', caption='bottom', width=150)
                if shoes_img:
                    st.image(shoes_img.path, caption='shoes', width=150)
                if accessory_img:
                    st.image(accessory_img.path, caption='accessory', width=150)
            except Exception as e:
                st.error(f"画像の読み込みエラー: {e}")

            if st.button(f'好きから解除 {favorite.id}', key=f'remove_fav_{favorite.id}'):
                session.delete(favorite)
                session.commit()
                st.success(f'好き {favorite.id} を解除しました')
                st.rerun()

    elif page == 'データベースバックアップ':
        st.header('データベースバックアップ')
        if st.button('バックアップを作成'):
            backup_file = create_backup()
            st.success("バックアップが作成されました。")
            with open(backup_file, 'rb') as f:
                st.download_button(label="バックアップをダウンロード", data=f, file_name='fashion_backup.zip')

        st.header('バックアップの復元')
        uploaded_backup = st.file_uploader("バックアップZIPファイルを選択...", type=["zip"])
        if uploaded_backup is not None:
            backup_path = os.path.join(BACKUP_DIR, uploaded_backup.name)
            with open(backup_path, 'wb') as f:
                f.write(uploaded_backup.getbuffer())
            try:
                restore_backup(backup_path)
                st.success("バックアップが正常に復元されました。")
            except Exception as e:
                st.error(f"バックアップの復元エラー: {e}")

    # Load images from directory into the database (if not already present)
    load_images_from_directory()
