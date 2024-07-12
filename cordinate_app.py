import os
import random
import sys
import shutil
import zipfile
import io
from PIL import Image as PILImage
import pillow_heif
import imageio.v3 as iio
import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

# 定数の定義
UPLOAD_DIR = 'uploads'
BACKUP_DIR = 'backups'
ALLOWED_EXTENSIONS = {'jpg', 'png', 'jpeg', 'heic'}
MAX_USERNAME_LENGTH = 50
MIN_PASSWORD_LENGTH = 8

# データベースの設定
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(MAX_USERNAME_LENGTH), unique=True, nullable=False)
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

# データベースエンジンとセッションの作成
engine = create_engine('sqlite:///fashion.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# ディレクトリの作成
for directory in [UPLOAD_DIR, BACKUP_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# セッション状態の初期化
for state in ["dislike_button_clicked", "favorite_button_clicked", "logged_in_user"]:
    if state not in st.session_state:
        st.session_state[state] = None if state == "logged_in_user" else False

# ユーティリティ関数
def hash_password(password):
    return generate_password_hash(password)

def check_password(hashed_password, plain_password):
    return check_password_hash(hashed_password, plain_password)

def authenticate(username, password):
    user = session.query(User).filter(User.username == username).first()
    if user and check_password(user.password, password):
        return user
    return None

def register(username, password):
    if len(username) > MAX_USERNAME_LENGTH:
        return None, "ユーザー名が長すぎます"
    if len(password) < MIN_PASSWORD_LENGTH:
        return None, "パスワードが短すぎます"
    
    hashed_password = hash_password(password)
    new_user = User(username=username, password=hashed_password)
    try:
        session.add(new_user)
        session.commit()
        return new_user, None
    except IntegrityError:
        session.rollback()
        return None, "ユーザー名は既に存在します"

def create_backup():
    backup_file = os.path.join(BACKUP_DIR, 'fashion_backup.zip')
    with zipfile.ZipFile(backup_file, 'w') as zipf:
        zipf.write('fashion.db', os.path.basename('fashion.db'))
        for root, _, files in os.walk(UPLOAD_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, UPLOAD_DIR)
                zipf.write(file_path, arcname)
    return backup_file

def restore_backup(backup_file):
    with zipfile.ZipFile(backup_file, 'r') as zipf:
        temp_dir = os.path.join(BACKUP_DIR, 'temp_restore')
        zipf.extractall(temp_dir)
        
        db_path = os.path.join(temp_dir, 'fashion.db')
        if os.path.exists(db_path):
            shutil.move(db_path, 'fashion.db')

        for user_dir in os.listdir(temp_dir):
            user_dir_path = os.path.join(temp_dir, user_dir)
            if os.path.isdir(user_dir_path) and user_dir != 'fashion.db':
                user_upload_dir = os.path.join(UPLOAD_DIR, user_dir)
                if not os.path.exists(user_upload_dir):
                    os.makedirs(user_upload_dir)
                for root, _, files in os.walk(user_dir_path):
                    for file_ in files:
                        src_file = os.path.join(root, file_)
                        relative_path = os.path.relpath(src_file, user_dir_path)
                        dst_file = os.path.join(user_upload_dir, relative_path)
                        dst_dir = os.path.dirname(dst_file)
                        if not os.path.exists(dst_dir):
                            os.makedirs(dst_dir)
                        shutil.copy2(src_file, dst_file)

        shutil.rmtree(temp_dir)

def load_images_from_directory(user):
    user_upload_dir = os.path.join(UPLOAD_DIR, user.username)
    if not os.path.exists(user_upload_dir):
        os.makedirs(user_upload_dir)
    
    for file_name in os.listdir(user_upload_dir):
        file_path = os.path.join(user_upload_dir, file_name)
        if not session.query(Image).filter_by(path=file_path, user_id=user.id).first():
            category = 'uncategorized'
            new_image = Image(category=category, path=file_path, user_id=user.id)
            session.add(new_image)
    session.commit()

def get_images_by_category(category, user_id):
    return session.query(Image).filter_by(category=category.lower(), user_id=user_id).all()

def get_random_image(category, user_id):
    images = get_images_by_category(category, user_id)
    return random.choice(images) if images else None

def is_disliked_combination(top, bottom, shoes, accessory, user_id):
    if top and bottom:
        dislike = session.query(Dislike).filter_by(
            top_id=top.id, bottom_id=bottom.id, 
            shoes_id=shoes.id if shoes else None, 
            accessory_id=accessory.id if accessory else None, 
            user_id=user_id
        ).first()
        return dislike is not None
    return False

def get_random_suggestion(include_shoes, include_accessory, user_id):
    attempts = 0
    max_attempts = 10
    while attempts < max_attempts:
        top = get_random_image('top', user_id)
        bottom = get_random_image('bottom', user_id)
        shoes = get_random_image('shoes', user_id) if include_shoes else None
        accessory = get_random_image('accessory', user_id) if include_accessory else None
        if top and bottom and not is_disliked_combination(top, bottom, shoes, accessory, user_id):
            return top, bottom, shoes, accessory
        attempts += 1
    return None, None, None, None

def check_combination_exists(top_id, bottom_id, shoes_id, accessory_id, user_id, table):
    return session.query(table).filter_by(
        top_id=top_id, bottom_id=bottom_id, shoes_id=shoes_id, accessory_id=accessory_id, user_id=user_id
    ).first() is not None

# Streamlitアプリ
def main():
    st.title('ファッション提案アプリ')

    if st.session_state["logged_in_user"] is None:
        login_page()
    else:
        logged_in_page()

def login_page():
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
        new_user, error_message = register(new_username, new_password)
        if new_user:
            st.success("登録成功")
        else:
            st.error(error_message)

def logged_in_page():
    user = st.session_state["logged_in_user"]
    st.sidebar.text(f"ログイン中: {user.username}")
    if st.sidebar.button("ログアウト"):
        st.session_state["logged_in_user"] = None
        st.rerun()

    page = st.sidebar.selectbox('ページを選択', ['画像をアップロード', 'コーディネート提案', 'お気に入りの編集', '嫌いな組み合わせの編集', 'データベースバックアップ'])

    if page == '画像をアップロード':
        upload_page(user)
    elif page == 'コーディネート提案':
        suggestion_page(user)
    elif page == '嫌いな組み合わせの編集':
        dislike_page(user)
    elif page == 'お気に入りの編集':
        favorite_page(user)
    elif page == 'データベースバックアップ':
        backup_page()

    load_images_from_directory(user)

def upload_page(user):
    st.header('画像をアップロード')
    category = st.selectbox('カテゴリー', ['top', 'bottom', 'shoes', 'accessory'])
    uploaded_file = st.file_uploader("画像を選択...", type=list(ALLOWED_EXTENSIONS))

    if uploaded_file is not None:
        try:
            st.write(f"アップロードされたファイル: {uploaded_file.name}")
            pillow_heif.register_heif_opener()

            file_name = uploaded_file.name.lower()
            uploaded_file_bytes = uploaded_file.read()
            byte_stream = io.BytesIO(uploaded_file_bytes)
            img = PILImage.open(byte_stream)

            user_upload_dir = os.path.join(UPLOAD_DIR, user.username)
            if not os.path.exists(user_upload_dir):
                os.makedirs(user_upload_dir)

            file_path = os.path.join(user_upload_dir, uploaded_file.name)
            img.save(file_path)
            new_image = Image(category=category.lower(), path=file_path, user_id=user.id)
            session.add(new_image)
            session.commit()
            st.success(f"{uploaded_file.name} を {category} カテゴリーにアップロードしました。")
        except Exception as e:
            st.error(f"ファイルのアップロードエラー: {e}")

    display_uploaded_images(user)

def display_uploaded_images(user):
    st.header('アップロードされた画像')
    try:
        images = session.query(Image).filter_by(user_id=user.id).all()
        for image in images:
            try:
                st.image(image.path, caption=f"{image.category} (ID: {image.id})", width=150)
                if st.button(f'削除 {image.id}', key=f'delete_{image.id}'):
                    delete_image(image)
                    st.rerun()
            except Exception as e:
                st.error(f"画像の読み込みエラー: {e}")
    except Exception as e:
        st.error(f"データベースクエリエラー: {e}")

def delete_image(image):
    try:
        if os.path.exists(image.path):
            os.remove(image.path)
        session.delete(image)
        session.commit()
        st.success(f"画像 {image.id} を削除しました")
    except Exception as e:
        st.error(f"画像の削除エラー: {e}")

def suggestion_page(user):
    st.header('ランダムなコーディネート提案')
    include_shoes = st.checkbox('shoesを含む', value=True)
    include_accessory = st.checkbox('accessoryを含む', value=True)

    if st.button('コーディネート提案'):
        top, bottom, shoes, accessory = get_random_suggestion(include_shoes, include_accessory, user.id)
        st.session_state.update({"top": top, "bottom": bottom, "shoes": shoes, "accessory": accessory})

    display_suggestion()
    handle_feedback(user)

def display_suggestion():
    if "top" in st.session_state and st.session_state["top"] and st.session_state["bottom"]:
        for item in ["top", "bottom", "shoes", "accessory"]:
            if st.session_state[item]:
                st.subheader(item)
                st.image(st.session_state[item].path, width=150)
    else:
        st.error("新しい提案を生成できませんでした。もっと画像をアップロードするか、嫌いな組み合わせを調整してください。")

def handle_feedback(user):
    st.header('フィードバック')
    if st.button('この組み合わせは嫌い'):
        st.session_state["dislike_button_clicked"] = True

    if st.session_state["dislike_button_clicked"]:
        handle_dislike(user)

    if st.button('この組み合わせは好き'):
        st.session_state["favorite_button_clicked"] = True

    if st.session_state["favorite_button_clicked"]:
        handle_favorite(user)

def handle_dislike(user):
    if st.session_state["top"] and st.session_state["bottom"]:
        if not check_combination_exists(
            st.session_state["top"].id, st.session_state["bottom"].id,
            st.session_state["shoes"].id if st.session_state["shoes"] else None,
            st.session_state["accessory"].id if st.session_state["accessory"] else None,
            user.id, Dislike
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

def handle_favorite(user):
    if st.session_state["top"] and st.session_state["bottom"]:
        if not check_combination_exists(
            st.session_state["top"].id, st.session_state["bottom"].id,
            st.session_state["shoes"].id if st.session_state["shoes"] else None,
            st.session_state["accessory"].id if st.session_state["accessory"] else None,
            user.id, Favorite
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

def dislike_page(user):
    st.header('嫌いな組み合わせ')
    try:
        disliked_combinations = session.query(Dislike).filter_by(user_id=user.id).all()
        for dislike in disliked_combinations:
            display_combination(dislike, 'dislike')
            if st.button(f'嫌いを解除 {dislike.id}', key=f'remove_dislike_{dislike.id}'):
                session.delete(dislike)
                session.commit()
                st.success(f'嫌い {dislike.id} を解除しました')
                st.rerun()
    except Exception as e:
        st.error(f"データベースクエリエラー: {e}")

def favorite_page(user):
    st.header('好きな組み合わせ')
    try:
        favorite_combinations = session.query(Favorite).filter_by(user_id=user.id).all()
        for favorite in favorite_combinations:
            display_combination(favorite, 'favorite')
            if st.button(f'好きから解除 {favorite.id}', key=f'remove_fav_{favorite.id}'):
                session.delete(favorite)
                session.commit()
                st.success(f'好き {favorite.id} を解除しました')
                st.rerun()
    except Exception as e:
        st.error(f"データベースクエリエラー: {e}")

def display_combination(combination, combination_type):
    st.write(f"{combination_type.capitalize()}な組み合わせ:")
    for item in ['top', 'bottom', 'shoes', 'accessory']:
        item_id = getattr(combination, f'{item}_id')
        if item_id:
            img = session.query(Image).filter_by(id=item_id).first()
            if img:
                try:
                    st.image(img.path, caption=item, width=150)
                except Exception as e:
                    st.error(f"画像の読み込みエラー: {e}")

def backup_page():
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

if __name__ == "__main__":
    main()