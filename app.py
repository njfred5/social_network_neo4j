# social_network.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dataclasses import dataclass
from typing import List, Optional
from neo4j import GraphDatabase

# ======================
# Database Access Layer
# ======================

from neo4j import GraphDatabase

class Database:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    # ======================
    # USER OPERATIONS
    # ======================
    def create_user(self, username: str, name: str) -> int:
        query = """
        CREATE (u:User {id: $id, username: $username, name: $name})
        RETURN u.id AS id
        """
        # teacher wants integer IDs → we generate them manually
        with self.driver.session() as session:
            # get max existing id
            max_id = session.run("MATCH (u:User) RETURN coalesce(max(u.id), 0) AS max").single()["max"]
            new_id = max_id + 1

            result = session.run(query, id=new_id, username=username, name=name)
            return result.single()["id"]

    def get_user(self, user_id: int):
        query = """
        MATCH (u:User {id: $id})
        RETURN u
        """
        with self.driver.session() as session:
            record = session.run(query, id=user_id).single()
            if record:
                u = record["u"]
                return {"id": u["id"], "username": u["username"], "name": u["name"]}
            return None

    def get_all_users(self):
        query = "MATCH (u:User) RETURN u ORDER BY u.id"
        with self.driver.session() as session:
            return [
                {"id": u["u"]["id"], "username": u["u"]["username"], "name": u["u"]["name"]}
                for u in session.run(query)
            ]

    # ======================
    # POST OPERATIONS
    # ======================
    def create_post(self, user_id: int, content: str) -> int:
        query = """
        MATCH (u:User {id: $user_id})
        WITH u
        OPTIONAL MATCH (p:Post)
        WITH u, coalesce(max(p.id), 0) + 1 AS new_id
        CREATE (u)-[:POSTED]->(p:Post {
            id: new_id,
            content: $content,
            timestamp: datetime()
        })
        RETURN p.id AS id
        """
        with self.driver.session() as session:
            return session.run(query, user_id=user_id, content=content).single()["id"]

    def get_posts_by_user(self, user_id: int):
        query = """
        MATCH (u:User {id: $id})-[:POSTED]->(p:Post)
        RETURN p, u
        ORDER BY p.timestamp DESC
        """
        with self.driver.session() as session:
            return [
                {
                    "id": r["p"]["id"],
                    "content": r["p"]["content"],
                    "timestamp": r["p"]["timestamp"],
                    "username": r["u"]["username"],
                    "name": r["u"]["name"]
                }
                for r in session.run(query, id=user_id)
            ]

    # ======================
    # FOLLOW OPERATIONS
    # ======================
    def follow_user(self, follower_id: int, followee_id: int):
        query = """
        MATCH (a:User {id: $follower}), (b:User {id: $followee})
        MERGE (a)-[:FOLLOWS]->(b)
        """
        with self.driver.session() as session:
            session.run(query, follower=follower_id, followee=followee_id)
            return True

    def unfollow_user(self, follower_id: int, followee_id: int):
        query = """
        MATCH (a:User {id: $follower})-[r:FOLLOWS]->(b:User {id: $followee})
        DELETE r
        """
        with self.driver.session() as session:
            result = session.run(query, follower=follower_id, followee=followee_id)
            return True

    def get_followers(self, user_id: int):
        query = """
        MATCH (u:User {id: $id})<-[:FOLLOWS]-(f:User)
        RETURN f
        """
        with self.driver.session() as session:
            return [
                {"id": r["f"]["id"], "username": r["f"]["username"], "name": r["f"]["name"]}
                for r in session.run(query, id=user_id)
            ]

    def get_following(self, user_id: int):
        query = """
        MATCH (u:User {id: $id})-[:FOLLOWS]->(f:User)
        RETURN f
        """
        with self.driver.session() as session:
            return [
                {"id": r["f"]["id"], "username": r["f"]["username"], "name": r["f"]["name"]}
                for r in session.run(query, id=user_id)
            ]

    # ======================
    # FEED
    # ======================
    def get_feed(self, user_id: int):
        query = """
        MATCH (me:User {id: $id})-[:FOLLOWS]->(u:User)-[:POSTED]->(p:Post)
        RETURN p, u
        ORDER BY p.timestamp DESC
        """
        with self.driver.session() as session:
            return [
                {
                    "id": r["p"]["id"],
                    "content": r["p"]["content"],
                    "timestamp": r["p"]["timestamp"],
                    "username": r["u"]["username"],
                    "name": r["u"]["name"]
                }
                for r in session.run(query, id=user_id)
            ]


# ======================
# Web Application
# ======================
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
db = Database(
    uri="neo4j+s://3a1fff2f.databases.neo4j.io",
    user="3a1fff2f",
    password="K7G9XTVGMexZKK98DNHqraCM5wl2yVL2_7x7VPV6kaw"
)


# Sample data initializatio

# ======================
# API Endpoints
# ======================
@app.route('/api/users', methods=['GET'])
def api_get_users():
    return jsonify(db.get_all_users())

@app.route('/api/users/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    user = db.get_user(user_id)
    return jsonify(user) if user else ('User not found', 404)

@app.route('/api/users/<int:user_id>/posts', methods=['GET'])
def api_get_user_posts(user_id):
    return jsonify(db.get_posts_by_user(user_id))

@app.route('/api/users/<int:user_id>/feed', methods=['GET'])
def api_get_user_feed(user_id):
    return jsonify(db.get_feed(user_id))

@app.route('/api/users/<int:user_id>/followers', methods=['GET'])
def api_get_user_followers(user_id):
    return jsonify(db.get_followers(user_id))

@app.route('/api/users/<int:user_id>/following', methods=['GET'])
def api_get_user_following(user_id):
    return jsonify(db.get_following(user_id))

@app.route('/api/posts', methods=['POST'])
def api_create_post():
    data = request.get_json()
    post_id = db.create_post(data['user_id'], data['content'])
    return jsonify({'post_id': post_id}), 201

@app.route('/api/follow', methods=['POST'])
def api_follow_user():
    data = request.get_json()
    success = db.follow_user(data['follower_id'], data['followee_id'])
    return jsonify({'success': success}), 201 if success else 200

# ======================
# Frontend Routes
# ======================
@app.route('/')
def home():
    users = db.get_all_users()
    current_user = None
    if 'user_id' in session:
        current_user = db.get_user(session['user_id'])
    return render_template('index.html', users=users, current_user=current_user)

@app.route('/user/<int:user_id>')
def user_profile(user_id):
    user = db.get_user(user_id)
    if not user:
        return "User not found", 404
        
    current_user = None
    is_following = False
    
    if 'user_id' in session:
        current_user = db.get_user(session['user_id'])
        if current_user and current_user['id'] != user_id:
            # Check if current user is following this profile user
            following = db.get_following(current_user['id'])
            is_following = any(f['id'] == user_id for f in following)
    
    posts = db.get_posts_by_user(user_id)
    followers = db.get_followers(user_id)
    following = db.get_following(user_id)
    
    return render_template('profile.html', 
                         user=user, 
                         posts=posts,
                         followers=followers,
                         following=following,
                         current_user=current_user,
                         is_following=is_following)

@app.route('/user/<int:user_id>/feed')
def user_feed(user_id):
    user = db.get_user(user_id)
    feed = db.get_feed(user_id)
    return render_template('feed.html', user=user, feed=feed)

@app.route('/create_post', methods=['POST'])
def create_post():
    user_id = int(request.form['user_id'])
    content = request.form['content']
    db.create_post(user_id, content)
    return redirect(url_for('user_profile', user_id=user_id))

@app.route('/login/<int:user_id>')
def login(user_id):
    session['user_id'] = user_id
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/follow', methods=['POST'])
def follow():
    follower_id = int(request.form['follower_id'])
    followee_id = int(request.form['followee_id'])
    
    # Check if the user is already following
    following = db.get_following(follower_id)
    is_following = any(f['id'] == followee_id for f in following)
    
    if is_following:
        # Implement unfollow functionality (you'll need to add this to your Database class)
        db.unfollow_user(follower_id, followee_id)
    else:
        db.follow_user(follower_id, followee_id)
    
    return redirect(url_for('user_profile', user_id=followee_id))

# ======================
# HTML Templates
# ======================
@app.route('/templates/<template_name>')
def serve_template(template_name):
    return render_template(template_name)

# Template rendering functions
app.jinja_env.globals.update(
    render_index=lambda: render_template('index.html', users=db.get_all_users()),
    render_profile=lambda user_id: render_template(
        'profile.html',
        user=db.get_user(user_id),
        posts=db.get_posts_by_user(user_id),
        followers=db.get_followers(user_id),
        following=db.get_following(user_id)
    )
)

if __name__ == '__main__':
    app.run(debug=True)